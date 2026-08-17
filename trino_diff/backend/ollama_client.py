import json
import urllib.request
import urllib.error
import re


def query_ollama(
    prompt: str,
    system: str = "",
    model: str = "qwen2.5-coder:1.5b",
    base_url: str = "http://localhost:11434",
    timeout: int = 90
) -> dict:
    """
    Query a local Ollama instance for text generation using /api/chat or /api/generate with system prompt.
    Returns dict with 'success': bool, 'response': str, 'error': str.
    """
    # Try /api/chat first as it adheres best to instruction/coder system roles
    chat_endpoint = f"{base_url.rstrip('/')}/api/chat"
    messages = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})

    chat_payload = {
        "model": model,
        "messages": messages,
        "stream": False,
        "options": {
            "temperature": 0.1,
            "top_p": 0.9,
        }
    }

    try:
        data = json.dumps(chat_payload).encode("utf-8")
        req = urllib.request.Request(
            chat_endpoint,
            data=data,
            headers={"Content-Type": "application/json"},
            method="POST"
        )
        with urllib.request.urlopen(req, timeout=timeout) as response:
            if response.status == 200:
                result = json.loads(response.read().decode("utf-8"))
                generated_text = result.get("message", {}).get("content", "")
                if generated_text:
                    return {"success": True, "response": generated_text, "error": ""}
    except Exception:
        # Fallback to /api/generate if /api/chat is unavailable
        pass

    # Fallback /api/generate
    gen_endpoint = f"{base_url.rstrip('/')}/api/generate"
    gen_payload = {
        "model": model,
        "prompt": prompt,
        "stream": False,
        "options": {
            "temperature": 0.1,
            "top_p": 0.9,
        }
    }
    if system:
        gen_payload["system"] = system

    try:
        data = json.dumps(gen_payload).encode("utf-8")
        req = urllib.request.Request(
            gen_endpoint,
            data=data,
            headers={"Content-Type": "application/json"},
            method="POST"
        )
        with urllib.request.urlopen(req, timeout=timeout) as response:
            if response.status == 200:
                result = json.loads(response.read().decode("utf-8"))
                generated_text = result.get("response", "")
                return {"success": True, "response": generated_text, "error": ""}
            else:
                return {
                    "success": False,
                    "response": "",
                    "error": f"Ollama HTTP error {response.status}: {response.reason}"
                }
    except urllib.error.URLError as e:
        return {
            "success": False,
            "response": "",
            "error": f"Could not connect to Ollama at {base_url}. Ensure Ollama is running (`ollama serve`). Details: {e.reason}"
        }
    except Exception as e:
        return {
            "success": False,
            "response": "",
            "error": f"Ollama request error: {str(e)}"
        }


def extract_sql_from_response(text: str) -> str:
    """
    Extract the SQL block from markdown code blocks in the model's response if present.
    """
    sql_blocks = re.findall(r"```(?:sql)?\s*([\s\S]*?)```", text, re.IGNORECASE)
    if sql_blocks:
        # Return the longest or last SQL block as the corrected query
        return max(sql_blocks, key=len).strip()
    return ""


def test_ollama_connection(base_url: str = "http://localhost:11434", model: str = "qwen2.5-coder:1.5b") -> tuple:
    """
    Test connectivity to Ollama and check if the requested model is installed.
    Returns (success: bool, message: str).
    """
    try:
        tags_url = f"{base_url.rstrip('/')}/api/tags"
        req = urllib.request.Request(tags_url, headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=5) as resp:
            if resp.status == 200:
                data = json.loads(resp.read().decode("utf-8"))
                models = [m.get("name", "") for m in data.get("models", [])]
                model_base = model.split(":")[0]
                model_found = any(m == model or m.startswith(model_base) for m in models)

                if model_found:
                    return True, f"Ollama is running. Model '{model}' is available."
                else:
                    avail = ", ".join(models) if models else "none"
                    return True, f"Ollama is running, but '{model}' was not found. Available models: {avail}. (Run `ollama pull {model}`)"
            return False, f"Ollama returned HTTP {resp.status}"
    except Exception as e:
        return False, f"Cannot connect to Ollama at {base_url}: {e}"
