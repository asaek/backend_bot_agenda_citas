"""Dobles de transporte: no invocan proveedores ni capturan dispositivos."""

import asyncio


class FakeVoiceMedia:
    def __init__(self):
        self.events, self.input_audio, self.output_events = asyncio.Queue(), asyncio.Queue(), asyncio.Queue()
        self.output_started = asyncio.Queue()
        self.last_received_at = None
        self.metrics = {"received_frames": 0, "non_silent_frames": 0}
        self.audio = []
        self.emitted_ms = {}
        self.closed = False
        self.close_count = 0

    async def negotiate(self, offer):
        return "voice-answer"

    def output_audio(self, item_id, pcm):
        self.audio.append((item_id, pcm))

    def output_done(self, item_id):
        pass

    def interrupt_output(self):
        emitted = dict(self.emitted_ms)
        self.audio.clear()
        return emitted

    async def close(self):
        self.close_count += 1
        self.closed = True


class FakeRealtimeProvider:
    def __init__(self):
        self.events = asyncio.Queue()
        self.commands = []
        self.responses = []
        self.closed = False
        self.close_count = 0
        self.instructions = None

    async def connect(self, instructions, tools, history):
        self.instructions, self.tools, self.history = instructions, tools, history

    async def send(self, event):
        self.commands.append(event)
        if event["type"] == "response.create":
            response = {"id": f"response-{len(self.responses)+1}", "metadata": event["response"]["metadata"]}
            self.responses.append(response)
            self.events.put_nowait({"type": "response.created", "response": response})
        elif event["type"] == "response.cancel":
            self.events.put_nowait({"type": "response.done", "response": {"id": event["response_id"], "status": "cancelled", "output": []}})

    async def receive(self):
        return await self.events.get()

    async def close(self):
        self.close_count += 1
        self.closed = True
