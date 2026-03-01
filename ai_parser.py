import json
import re
import pandas as pd
from concurrent.futures import ThreadPoolExecutor, as_completed
from openai import OpenAI
from config import (
    QWEN_MODEL_SCAN, QWEN_MODEL, DASHSCOPE_BASE_URL, METRIC_KEYS,
    PAGE_SCAN_PROMPT, SYSTEM_PROMPT, USER_PROMPT, SUMMARY_PROMPT,
    MAX_DETAIL_PAGES, SCAN_BATCH_SIZE,
)


def _null_result() -> dict:
    return {key: None for key in METRIC_KEYS}


def generate_summary(df: pd.DataFrame, api_key: str) -> list[str]:
    """
    Use qwen3.5-plus to generate 4-5 bullet point insights
    from the completed comparison DataFrame. Returns a list of strings.
    """
    client = OpenAI(api_key=api_key, base_url=DASHSCOPE_BASE_URL)

    table_text = df.to_string()
    prompt = SUMMARY_PROMPT.format(table=table_text)

    response = client.chat.completions.create(
        model=QWEN_MODEL,
        messages=[{"role": "user", "content": prompt}],
        max_tokens=512,
    )

    raw = response.choices[0].message.content.strip()

    bullets = []
    for line in raw.splitlines():
        line = line.strip()
        if line:
            # Normalise leading dash/bullet characters
            line = re.sub(r"^[-•*]\s*", "", line)
            bullets.append(line)

    return bullets or ["No summary could be generated."]


def _build_image_content(images: list[str], label_prefix: str = "") -> list[dict]:
    """Build an OpenAI-compatible content list with optional [Page N] labels."""
    content = []
    for i, b64 in enumerate(images):
        if label_prefix:
            content.append({"type": "text", "text": f"[{label_prefix} {i + 1}]"})
        content.append({
            "type": "image_url",
            "image_url": {"url": f"data:image/png;base64,{b64}"},
        })
    return content


def _scan_batch(client: OpenAI, batch_images: list[str], batch_start: int) -> list[int]:
    """
    Scan a single batch of page thumbnails and return the 0-based indices
    of pages that contain financial summary tables.
    """
    content = [{"type": "text", "text": PAGE_SCAN_PROMPT}]
    for i, b64 in enumerate(batch_images):
        content.append({"type": "text", "text": f"[Page {batch_start + i + 1}]"})
        content.append({
            "type": "image_url",
            "image_url": {"url": f"data:image/png;base64,{b64}"},
        })

    response = client.chat.completions.create(
        model=QWEN_MODEL_SCAN,
        messages=[{"role": "user", "content": content}],
        max_tokens=128,
    )

    raw = response.choices[0].message.content.strip()
    raw = re.sub(r"^```(?:json)?\s*", "", raw)
    raw = re.sub(r"\s*```$", "", raw)

    try:
        page_nums = json.loads(raw)
        if not isinstance(page_nums, list):
            return []
        return [int(p) - 1 for p in page_nums if isinstance(p, (int, float))]
    except Exception:
        return []


def identify_relevant_pages(overview_images: list[str], api_key: str) -> list[int]:
    """
    Pass 1: split thumbnails into batches and scan them in parallel.

    Returns a sorted, deduplicated list of 0-based page indices (capped at
    MAX_DETAIL_PAGES). Falls back to the first 20 pages if nothing is found.
    """
    client = OpenAI(api_key=api_key, base_url=DASHSCOPE_BASE_URL)

    # Split into batches
    batches = [
        (overview_images[i : i + SCAN_BATCH_SIZE], i)
        for i in range(0, len(overview_images), SCAN_BATCH_SIZE)
    ]

    all_indices: list[int] = []
    with ThreadPoolExecutor(max_workers=len(batches)) as executor:
        futures = {
            executor.submit(_scan_batch, client, imgs, start): start
            for imgs, start in batches
        }
        for future in as_completed(futures):
            try:
                all_indices.extend(future.result())
            except Exception as e:
                print(f"[page scan] Batch starting at {futures[future]} failed: {e}")

    indices = sorted(set(all_indices))[:MAX_DETAIL_PAGES]
    if not indices:
        print("[page scan] No pages identified — using first 20 pages")
        return list(range(min(20, len(overview_images))))
    return indices


def extract_metrics(detail_images: list[str], bank_name: str, api_key: str) -> dict:
    """
    Pass 2: send high-res images of the selected pages to Qwen and extract
    the financial metrics as a JSON object.
    """
    client = OpenAI(api_key=api_key, base_url=DASHSCOPE_BASE_URL)

    content = _build_image_content(detail_images)
    content.append({"type": "text", "text": USER_PROMPT})

    response = client.chat.completions.create(
        model=QWEN_MODEL,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user",   "content": content},
        ],
        max_tokens=1024,
    )

    raw = response.choices[0].message.content.strip()
    raw = re.sub(r"^```(?:json)?\s*", "", raw)
    raw = re.sub(r"\s*```$", "", raw)

    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        print(f"[{bank_name}] JSON parse error. Raw response:\n{raw}")
        return _null_result()

    result = _null_result()
    for key in METRIC_KEYS:
        if key in data:
            result[key] = data[key]

    return result
