import logging
import os
from fastapi import FastAPI
from fastapi.responses import FileResponse

# --- OpenTelemetry TRACING Setup (START) ---
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.sdk.resources import Resource

# --- OpenTelemetry LOGGING Setup (START) ---
from opentelemetry._logs import set_logger_provider
from opentelemetry.sdk._logs import LoggerProvider as SDKLoggerProvider, LogRecordProcessor
from opentelemetry.sdk._logs.export import BatchLogRecordProcessor
from opentelemetry.exporter.otlp.proto.http._log_exporter import OTLPLogExporter

# --- Shared Resource Definition ---
# This resource applies to BOTH logs and traces,
# ensuring they share the same service.name label.
resource = Resource(attributes={
    "service.name": "fastapi-backend",
    "environment": "local-dev"
})

# --- TRACING Configuration ---
# 1. Set up the TracerProvider
trace_provider = TracerProvider(resource=resource)

# 2. Configure the OTLP Span Exporter (for Traces)
# This sends traces to Alloy's OTLP HTTP endpoint
# Use 'alloy' hostname when running in Docker, localhost when running locally
import os
alloy_host = os.getenv("ALLOY_HOST", "alloy")
trace_exporter = OTLPSpanExporter(
    endpoint=f"http://{alloy_host}:4319/v1/traces"
)

# 3. Use a BatchProcessor for efficiency
trace_provider.add_span_processor(
    BatchSpanProcessor(trace_exporter)
)
trace.set_tracer_provider(trace_provider)
tracer = trace.get_tracer(__name__)

# --- LOGGING Configuration ---
# 1. Set up the LoggerProvider
logger_provider = SDKLoggerProvider(resource=resource)

# 2. Configure the OTLP Log Exporter
log_exporter = OTLPLogExporter(
    endpoint=f"http://{alloy_host}:4319/v1/logs"
)

# 3. Use a BatchProcessor for efficiency
logger_provider.add_log_record_processor(BatchLogRecordProcessor(log_exporter))
set_logger_provider(logger_provider)
logger = logging.getLogger(__name__)


# --- FastAPI Application ---

# Determine the path to the frontend's index.html
# When running in Docker, the frontend is mounted at /app/frontend
frontend_file_path = os.path.join(
    os.path.dirname(__file__), "frontend", "index.html"
)
if not os.path.exists(frontend_file_path):
    logger.error(f"Frontend file not found at: {frontend_file_path}")
    print(f"Error: Frontend file not found at: {frontend_file_path}")
    # You might want to exit or handle this more gracefully
    # For now, we'll let it raise an error if the route is hit.

app = FastAPI()

# This is the "magic" line that auto-instruments FastAPI for tracing.
# It will create spans for every request.
FastAPIInstrumentor.instrument_app(app)


@app.get("/api/root")
async def api_root():
    # This log will now be correlated with a traceId
    logger.warning("API root endpoint (/api/root) was called", extra={"client.ip": "127.0.0.1"})
    return {"message": "Hello World. Log and Trace sent."}


@app.get("/error")
async def make_error():
    try:
        # This will be captured in a trace span as an error
        x = 1 / 0
    except ZeroDivisionError as e:
        # This log will also be correlated with the trace
        logger.error(
            "A simulated error occurred",
            exc_info=True,
            extra={"error.type": "ZeroDivisionError"}
        )
        return {"message": "Error log and trace span sent."}

@app.get("/")
async def serve_frontend():
    """Serves the frontend's index.html file."""
    if not os.path.exists(frontend_file_path):
        logger.error(f"Frontend file {frontend_file_path} not found.")
        return {"error": "Frontend not found"}, 404
    return FileResponse(frontend_file_path)
