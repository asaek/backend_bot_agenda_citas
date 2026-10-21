"""Comprueba Opus bidireccional en la Pi, sin Meta ni servidores ICE externos."""

import argparse
import asyncio
import importlib.metadata
import json
import math
import platform
import resource
import sys
import time
from fractions import Fraction
from pathlib import Path

import av
import numpy as np
from aiortc import (
    AudioStreamTrack,
    RTCConfiguration,
    RTCPeerConnection,
    RTCRtpSender,
)


class ToneTrack(AudioStreamTrack):
    def __init__(self, frequency: int) -> None:
        super().__init__()
        self.frequency = frequency
        self.samples_sent = 0
        self.started_at: float | None = None

    async def recv(self) -> av.AudioFrame:
        loop = asyncio.get_running_loop()
        if self.started_at is None:
            self.started_at = loop.time()
        await asyncio.sleep(max(0, self.started_at + self.samples_sent / 48000 - loop.time()))
        samples = np.arange(960, dtype=np.float64) + self.samples_sent
        pcm = (8000 * np.sin(2 * math.pi * self.frequency * samples / 48000)).astype(np.int16)
        frame = av.AudioFrame.from_ndarray(pcm.reshape(1, -1), format="s16", layout="mono")
        frame.sample_rate = 48000
        frame.pts = self.samples_sent
        frame.time_base = Fraction(1, 48000)
        self.samples_sent += 960
        return frame


async def receive(track, seconds: float) -> dict:
    frames = samples = crossings = non_silent = 0
    sum_squares = 0.0
    previous = 0.0
    while samples < seconds * 48000:
        frame = await track.recv()
        pcm = frame.to_ndarray()
        channels = len(frame.layout.channels)
        mono = pcm[0] if frame.format.is_planar else pcm.reshape(-1, channels)[:, 0]
        mono = mono.astype(np.float64)
        crossings += int(np.count_nonzero((mono[:-1] <= 0) & (mono[1:] > 0)))
        crossings += int(previous <= 0 < mono[0])
        previous = float(mono[-1])
        sum_squares += float(np.dot(mono, mono))
        non_silent += int(np.max(np.abs(mono)) > 500)
        frames += 1
        samples += len(mono)
    return {
        "frames": frames,
        "non_silent_frames": non_silent,
        "decoded_seconds": round(samples / 48000, 3),
        "rms_pcm16": round(math.sqrt(sum_squares / samples), 1),
        "frequency_hz": round(crossings / (samples / 48000), 1),
    }


def rss_mib() -> float:
    status = Path("/proc/self/status")
    if status.exists():
        line = next(item for item in status.read_text().splitlines() if item.startswith("VmRSS:"))
        return int(line.split()[1]) / 1024
    return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / (1024 * 1024)


async def probe(seconds: float) -> dict:
    started = time.monotonic()
    cpu_started = time.process_time()
    baseline = rss_mib()
    peers = [RTCPeerConnection(RTCConfiguration(iceServers=[])) for _ in range(2)]
    tracks = [ToneTrack(440), ToneTrack(880)]
    received = [asyncio.get_running_loop().create_future() for _ in range(2)]
    consumers = []
    try:
        for index, peer in enumerate(peers):
            peer.addTrack(tracks[index])
            peer.on("track", lambda track, index=index: received[index].set_result(track))
            opus = [c for c in RTCRtpSender.getCapabilities("audio").codecs if c.mimeType.lower() == "audio/opus"]
            if not opus:
                raise RuntimeError("Opus no disponible")
            peer.getTransceivers()[0].setCodecPreferences(opus)
        await peers[0].setLocalDescription(await peers[0].createOffer())
        await peers[1].setRemoteDescription(peers[0].localDescription)
        await peers[1].setLocalDescription(await peers[1].createAnswer())
        await peers[0].setRemoteDescription(peers[1].localDescription)
        for future in received:
            consumers.append(asyncio.create_task(receive(await future, seconds)))
        results = await asyncio.gather(*consumers)
        for result, expected in zip(results, (880, 440)):
            if result["non_silent_frames"] < result["frames"] * 0.9:
                raise AssertionError("No se recibio audio util suficiente")
            if abs(result["frequency_hz"] - expected) > expected * 0.05:
                raise AssertionError("La frecuencia recibida no coincide con la enviada")
        elapsed = time.monotonic() - started
        cpu = time.process_time() - cpu_started
        final_rss = rss_mib()
        usage = resource.getrusage(resource.RUSAGE_SELF)
        return {
            "mode": "laboratory_same_pi_two_peers",
            "python": platform.python_version(),
            "os": platform.platform(),
            "architecture": platform.machine(),
            "versions": {name: importlib.metadata.version(name) for name in ("aiortc", "av", "numpy", "cryptography", "pylibsrtp")},
            "opus_encoder": av.Codec("libopus", "w").name,
            "opus_decoder": av.Codec("opus", "r").name,
            "audio_880_received_by_peer_0": results[0],
            "audio_440_received_by_peer_1": results[1],
            "wall_seconds": round(elapsed, 3),
            "cpu_seconds_both_peers": round(cpu, 3),
            "cpu_percent_one_core_both_peers": round(cpu / elapsed * 100, 1),
            "rss_baseline_mib": round(baseline, 2),
            "rss_final_mib": round(final_rss, 2),
            "rss_peak_mib": round(max(final_rss, usage.ru_maxrss / (1024 if sys.platform == "linux" else 1024 * 1024)), 2),
        }
    finally:
        for task in consumers:
            task.cancel()
        await asyncio.gather(*consumers, return_exceptions=True)
        for track in tracks:
            track.stop()
        await asyncio.gather(*(peer.close() for peer in peers))
        if any(peer.connectionState != "closed" for peer in peers):
            raise AssertionError("Conexion sin liberar")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seconds", type=float, default=5)
    args = parser.parse_args()
    if not 1 <= args.seconds <= 60:
        parser.error("--seconds debe estar entre 1 y 60")
    result = asyncio.run(asyncio.wait_for(probe(args.seconds), timeout=args.seconds + 20))
    result["connections_closed"] = True
    print(json.dumps(result, indent=2))
