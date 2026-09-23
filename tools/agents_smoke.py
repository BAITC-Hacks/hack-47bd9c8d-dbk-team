"""Smoke test + canonical example: openai-agents SDK against the Baiterek gateway.

Run:  set -a; . .env; set +a; .venv/bin/python agents_smoke.py
"""
import os

os.environ["OPENAI_AGENTS_DISABLE_TRACING"] = "1"  # tracing posts to OpenAI, not our gateway

from openai import AsyncOpenAI
from agents import Agent, Runner, OpenAIChatCompletionsModel, set_default_openai_client

client = AsyncOpenAI(
    base_url=f"https://{os.environ['BAITEREK_LLM_GATEWAY_URL']}/v1",
    api_key=os.environ["BAITEREK_LLM_GATEWAY_API_KEY"],
)
set_default_openai_client(client)

# ChatCompletionsModel works against both Baiterek and the GLM bridge (chat-only).
# Any gateway model id works here: deepseek-v4-1-flash, kimi-k3, qwen3-8-27b-fp8, ...
agent = Agent(
    name="smoke",
    instructions="Answer in one word.",
    model=OpenAIChatCompletionsModel(model="deepseek-v4-1-flash", openai_client=client),
)

if __name__ == "__main__":
    result = Runner.run_sync(agent, "Say: ok")
    assert result.final_output.strip(), "empty reply"
    print("agent reply:", result.final_output)
