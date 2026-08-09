import os
import textwrap

from dotenv import load_dotenv
from livekit.agents import Agent, AgentServer, AgentSession, JobContext, cli, room_io
from livekit.plugins import ai_coustics, google

# Keep local development credentials out of source control. Values already supplied
# by the deployment environment take precedence over either file.
load_dotenv(".env")
load_dotenv(".env.local")

DEFAULT_GEMINI_LIVE_MODEL = "gemini-2.5-flash-native-audio-preview-12-2025"
DEFAULT_GEMINI_LIVE_VOICE = "Puck"

VOICE_INSTRUCTIONS = textwrap.dedent(
    """\
    You are Plan A, a warm and concise voice companion for starting travel plans.

    Keep the conversation natural and easy to follow. Reply in plain spoken language,
    keep answers brief, and ask one question at a time. Do not use markdown, lists,
    emojis, or technical language. For now, focus on welcoming the user and helping
    them talk through a trip idea rather than making bookings or claiming live travel
    information.
    """
).strip()


def create_gemini_live_model() -> google.realtime.RealtimeModel:
    """Create a direct, server-side connection to the Gemini Live API."""
    api_key = os.getenv("GOOGLE_API_KEY")
    if not api_key:
        raise RuntimeError(
            "GOOGLE_API_KEY is required to connect the voice agent to Gemini Live."
        )

    return google.realtime.RealtimeModel(
        api_key=api_key,
        instructions=VOICE_INSTRUCTIONS,
        model=os.getenv("GEMINI_LIVE_MODEL", DEFAULT_GEMINI_LIVE_MODEL),
        temperature=0.8,
        voice=os.getenv("GEMINI_LIVE_VOICE", DEFAULT_GEMINI_LIVE_VOICE),
    )


def create_audio_input_options() -> room_io.AudioInputOptions:
    """Isolate the primary speaker before their audio reaches Gemini Live."""
    return room_io.AudioInputOptions(
        noise_cancellation=ai_coustics.audio_enhancement(
            model=ai_coustics.EnhancerModel.QUAIL_VF_S,
        )
    )


class Assistant(Agent):
    def __init__(self) -> None:
        super().__init__(instructions=VOICE_INSTRUCTIONS)


server = AgentServer()


@server.rtc_session(agent_name="plana-voice")
async def my_agent(ctx: JobContext) -> None:
    ctx.log_context_fields = {"room": ctx.room.name}

    # Gemini Live handles audio input, audio output, and turn detection directly.
    # LiveKit Cloud applies QUAIL_VF_S to the incoming user track before it reaches
    # Gemini, so nearby voices and environmental noise do not interfere with turns.
    session = AgentSession(llm=create_gemini_live_model())

    await session.start(
        agent=Assistant(),
        room=ctx.room,
        room_options=room_io.RoomOptions(
            audio_input=create_audio_input_options(),
        ),
    )
    await ctx.connect()
    await session.generate_reply(
        instructions="Greet the user briefly and invite them to start planning a trip."
    )


if __name__ == "__main__":
    cli.run_app(server)
