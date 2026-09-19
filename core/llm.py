import os
from dotenv import load_dotenv

# Load environment variables from .env if present
load_dotenv()

from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_google_genai.chat_models import GoogleRateLimitError
from tenacity import retry, retry_if_exception, stop_after_attempt, wait_exponential

# Mistral integration
try:
    from langchain_mistralai import ChatMistralAI
except ImportError:
    # The package is optional; install it if you want Mistral fallback.
    ChatMistralAI = None

# gemini-3.6-flash is ~5 RPM / ~20 RPD on the free tier.
# Flash-Lite covers the same meeting-analysis work with a much higher free quota.
DEFAULT_MODEL = "gemini-3.5-flash-lite"
FALLBACK_MODELS = (
    "gemini-3.5-flash-lite",
    "gemini-3.1-flash-lite",
    "gemini-flash-lite-latest",
)


def _model_list() -> list[str]:
    preferred = os.getenv("GEMINI_MODEL", DEFAULT_MODEL)
    models = [preferred, *FALLBACK_MODELS]
    seen: list[str] = []
    for model in models:
        if model and model not in seen:
            seen.append(model)
    return seen


def get_llm(temperature: float = 0.2, model: str | None = None, force_gemini: bool = False):
    """Return an LLM instance."""
    
    gemini_model = model or os.getenv("GEMINI_MODEL", DEFAULT_MODEL)
    gemini_llm = ChatGoogleGenerativeAI(
        model=gemini_model,
        google_api_key=os.getenv("GEMINI_API_KEY"),
        temperature=temperature,
        max_retries=2,
    )
    
    if force_gemini:
        return gemini_llm

    # Try Mistral first
    mistral_key = os.getenv("MISTRAL_API_KEY")
    if mistral_key and ChatMistralAI is not None:
        try:
            mistral_model = os.getenv("MISTRAL_MODEL", "mistral-small-latest")
            mistral_llm = ChatMistralAI(
                model=mistral_model,
                api_key=mistral_key,
                temperature=temperature,
                max_retries=2,
            )
            return mistral_llm.with_fallbacks([gemini_llm])
        except Exception as exc:
            print(f"Mistral init failed ({exc}); falling back to Gemini")
    
    return gemini_llm


def _is_rate_limit(exc: BaseException) -> bool:
    if isinstance(exc, GoogleRateLimitError):
        return True
    text = str(exc).lower()
    return any(
        token in text
        for token in ("429", "resource exhausted", "rate limit", "quota")
    )


def _before_sleep(retry_state):
    sleep = 0
    if retry_state.next_action:
        sleep = retry_state.next_action.sleep
    print(
        f"Gemini rate limited. Retry {retry_state.attempt_number} "
        f"in {sleep:.0f}s..."
    )


@retry(
    retry=retry_if_exception(_is_rate_limit),
    wait=wait_exponential(multiplier=2, min=15, max=60),
    stop=stop_after_attempt(4),
    before_sleep=_before_sleep,
    reraise=True,
)
def invoke_with_retry(chain, payload):
    return chain.invoke(payload)


def invoke_with_fallback(make_chain, payload, temperature: float = 0.2):
    last_error: BaseException | None = None
    
    for model in _model_list():
        print(f"Using Gemini model: {model}")
        chain = make_chain(get_llm(temperature=temperature, model=model, force_gemini=True))
        try:
            return invoke_with_retry(chain, payload)
        except Exception as exc:
            last_error = exc
            if _is_rate_limit(exc):
                print(f"{model} is rate-limited. Trying a fallback model...")
                continue
            raise
    raise last_error or RuntimeError("Gemini request failed")
