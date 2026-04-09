import requests
import json
import logging

logger = logging.getLogger(__name__)

OLLAMA_URL = "http://localhost:11434/api/generate"
MODEL_NAME = "llama3.2:3b"

class LlmClassificationError(Exception):
    pass

def classify_intent(context: dict) -> dict:
    """
    Stage 5: REASON
    Passes fused process context to local Ollama API to classify intent.
    Strict JSON output is expected.
    """
    prompt = f"""
    You are Ghost-Admin, an autonomic server healing daemon.
    Analyze the following process context and classify its intent into one of:
    [WORKING_AS_INTENDED, DEGRADED_BUT_FUNCTIONAL, LEAKING, UNDER_ATTACK, UNKNOWN].
    
    Context:
    {json.dumps(context, indent=2)}
    
    Return ONLY a JSON object with this exact schema:
    {
        "intent": "<intent_category>",
        "confidence": <float between 0.0 and 1.0>,
        "action": "kill" | "escalate" | "ignore",
        "start_at_step": <integer 1 to 4>,
        "reason": "<string explanation>"
    }
    """
    
    try:
        response = requests.post(OLLAMA_URL, json={
            "model": MODEL_NAME,
            "prompt": prompt,
            "stream": False,
            "format": "json"
        }, timeout=15)
        response.raise_for_status()
        
        val = response.json()
        result = json.loads(val["response"])
        
        # Ensure schema
        if "intent" not in result or "confidence" not in result:
            raise LlmClassificationError("LLM response missing required schema fields.")
            
        return result
        
    except Exception as e:
        logger.error(f"Reasoning stage failed: {e}")
        # Fail safe
        return {
            "intent": "UNKNOWN",
            "confidence": 0.0,
            "action": "escalate",
            "reason": f"Inference failed: {e}"
        }
