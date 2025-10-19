from google.adk.agents import Agent
from google.adk.tools import google_search

root_agent = Agent(
    name="google_search_agent",
    model="gemini-2.0-flash-exp",
    description="Agent to answer questions using Google Search.",
    instruction="Answer the question using the Google Search tool when needed. Provide helpful and accurate responses.",
    tools=[google_search],
)
