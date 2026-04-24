"""Flight Booking Agent - Main application module."""

import logging
import os
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from typing import Any

import uvicorn
from dotenv import load_dotenv
from strands.models.litellm import LiteLLMModel
from strands.types.streaming import StreamEvent
from strands.types.tools import ToolChoice, ToolSpec

load_dotenv()


class MockModel(LiteLLMModel):
    """Mock model that returns fixed responses without API calls."""

    def __init__(self, mock_text: str, **kwargs: Any) -> None:
        super().__init__(model_id="anthropic/claude-sonnet-4-5-20250929")
        self._mock_text = mock_text

    async def stream(
        self,
        messages: Any,
        tool_specs: list[ToolSpec] | None = None,
        system_prompt: str | None = None,
        *,
        tool_choice: ToolChoice | None = None,
        system_prompt_content: Any = None,
        **kwargs: Any,
    ) -> AsyncGenerator[StreamEvent, None]:
        yield {"messageStart": {"role": "assistant"}}
        yield {"contentBlockStart": {"start": {}}}
        yield {"contentBlockDelta": {"delta": {"text": self._mock_text}}}
        yield {"contentBlockStop": {}}
        yield {"messageStop": {"stopReason": "end_turn"}}


BOOKING_MOCK_RESPONSE = (
    "Flight ID 1 is available with 84 seats at $250 per seat. "
    "Status: Available. The booking has been reserved successfully. "
    "Booking confirmed. Your booking number is BK-123456. "
    "Payment processed via credit card."
)

from dependencies import (
    get_db_manager,
    get_env,
)
from fastapi import FastAPI
from strands import Agent
from strands.multiagent.a2a import A2AServer
from tools import (
    FLIGHT_BOOKING_TOOLS,
    check_availability,
    confirm_booking,
    manage_reservation,
    process_payment,
    reserve_flight,
)

# Configure logging with basicConfig
logging.basicConfig(
    level=logging.INFO,  # Set the log level to INFO
    # Define log message format
    format="%(asctime)s,p%(process)s,{%(filename)s:%(lineno)d},%(levelname)s,%(message)s",
)
logger = logging.getLogger(__name__)

# LiteLLM model identifier for Anthropic Claude
MODEL_ID = "anthropic/claude-sonnet-4-5-20250929"
if os.getenv("MOCK_LLM"):
    litellm_model = MockModel(mock_text=BOOKING_MOCK_RESPONSE)
else:
    litellm_model = LiteLLMModel(model_id=MODEL_ID)

strands_agent = Agent(
    name="Flight Booking Agent",
    description="Flight booking and reservation management agent",
    tools=FLIGHT_BOOKING_TOOLS,
    callback_handler=None,
    model=litellm_model,
)

env_settings = get_env()
a2a_server = A2AServer(
    agent=strands_agent,
    http_url=env_settings.agent_url,
    serve_at_root=True,
)


@asynccontextmanager
async def lifespan(
    app: FastAPI,
):
    """Application lifespan manager."""
    # Setups before server startup
    get_db_manager()
    logger.info("Flight Booking Agent starting up")
    logger.info(f"Agent URL: {env_settings.agent_url}")
    logger.info(f"Listening on {env_settings.host}:{env_settings.port}")

    yield
    # Triggered after server shutdown
    logger.info("Flight Booking Agent shutting down")


app = FastAPI(title="Flight Booking Agent", lifespan=lifespan)


@app.get("/ping")
def ping():
    """Health check endpoint."""
    logger.debug("Ping endpoint called")
    return {"status": "healthy"}


@app.get("/api/health")
def health():
    """Health status endpoint."""
    logger.debug("Health endpoint called")
    return {"status": "healthy", "agent": "flight_booking"}


@app.post("/api/check-availability")
def api_check_availability(
    flight_id: int,
):
    """Check flight availability API endpoint."""
    logger.info(f"Checking availability for flight_id: {flight_id}")
    result = check_availability(flight_id)
    logger.debug(f"Availability check result: {result}")
    return {"result": result}


@app.post("/api/reserve-flight")
def api_reserve_flight(
    flight_id: int,
    passengers: list,
    requested_seats: list | None = None,
):
    """Reserve flight API endpoint."""
    logger.info(
        f"Reserving flight_id: {flight_id} "
        f"for {len(passengers)} passengers"
    )
    logger.debug(f"Passengers: {passengers}")
    logger.debug(f"Requested seats: {requested_seats}")
    result = reserve_flight(flight_id, passengers, requested_seats)
    logger.debug(f"Reservation result: {result}")
    return {"result": result}


@app.post("/api/confirm-booking")
def api_confirm_booking(
    booking_number: str,
):
    """Confirm booking API endpoint."""
    logger.info(f"Confirming booking: {booking_number}")
    result = confirm_booking(booking_number)
    logger.debug(f"Booking confirmation result: {result}")
    return {"result": result}


@app.post("/api/process-payment")
def api_process_payment(
    booking_number: str,
    payment_method: str,
    amount: float | None = None,
):
    """Process payment API endpoint."""
    logger.info(f"Processing payment for booking: {booking_number}")
    logger.debug(f"Payment method: {payment_method}, Amount: {amount}")
    result = process_payment(booking_number, payment_method, amount)
    logger.debug(f"Payment processing result: {result}")
    return {"result": result}


@app.get("/api/reservation/{booking_number}")
def api_get_reservation(
    booking_number: str,
):
    """Get reservation details API endpoint."""
    logger.info(f"Retrieving reservation: {booking_number}")
    result = manage_reservation(booking_number, "view")
    logger.debug(f"Reservation details: {result}")
    return {"result": result}


@app.delete("/api/reservation/{booking_number}")
def api_cancel_reservation(
    booking_number: str,
    reason: str = "User requested cancellation",
):
    """Cancel reservation API endpoint."""
    logger.info(f"Canceling reservation: {booking_number}")
    logger.debug(f"Cancellation reason: {reason}")
    result = manage_reservation(booking_number, "cancel", reason)
    logger.debug(f"Cancellation result: {result}")
    return {"result": result}


app.mount("/", a2a_server.to_fastapi_app())


def main() -> None:
    """Main entry point for the application."""
    logger.info("Starting Flight Booking Agent server")
    uvicorn.run(app, host=env_settings.host, port=env_settings.port)


if __name__ == "__main__":
    main()
