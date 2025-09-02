from fastapi import FastAPI, File, Form, UploadFile
from fastapi.middleware.cors import CORSMiddleware
import json
import base64
from difflib import get_close_matches
import boto3
from PIL import Image
import io
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.application import MIMEApplication
import os
from typing import List, Dict, Any, Optional, Tuple
import pandas as pd
from botocore.config import Config

app = FastAPI(root_path="/api")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], 
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

config = Config(region_name="us-west-2", retries={"max_attempts": 10, "mode": "standard"})
bedrock_client = boto3.client("bedrock-runtime", config=config)

MODEL_IMAGE = "anthropic.claude-3-haiku-20240307-v1:0"
MODEL_TEXT = "anthropic.claude-3-sonnet-20240229-v1:0"

KB_ROWS: pd.DataFrame = pd.DataFrame()
KB_MAP: Dict[Tuple[str, str, str, str], Dict[str, Any]] = {} 
KB_COMPONENTS_BY_BMR: Dict[Tuple[str, str, str], List[str]] = {}  

COMPONENT_SYNONYMS = {
    "trunk lid": "Dickey Panel",
    "dickey": "Dickey Panel",
    "dicky": "Dickey Panel",  
    "dickey door": "Dickey Panel",
    "dickey panel": "Dickey Panel",
    "boot": "Dickey Panel",
    "rear panel": "Back Panel/ Skirt Panel",
    "headlights": "Headlight Left",
    "front lights": "Headlight Left",
    "taillights": "Tail light",
    "taillight": "Tail light",
    "tail light": "Tail light",
    "damaged headlight": "Headlight Left",
    "broken headlight": "Headlight Left",
    "bonnet": "Bonnet Hood",
    "hood": "Bonnet Hood",
    "bumper front": "Bumper Front",
    "bumper rear": "Bumper Rear",
    "front bumper": "Bumper Front",
    "bumper holder": "Bumper Holder Rear",   
    "Bumper Holder Rear": "Bumper Holder Rear" 
}

def _norm(s: Optional[str]) -> str:
    return str(s).strip() if s else ""

def _norm_key(s: str) -> str:
    return s.strip().lower().replace(" ", "")

def _parse_cost(val: Any) -> Optional[float]:
    if val is None:
        return None
    s = str(val).strip()
    if s == "" or s.lower() == "atpar":
        return None
    try:
        return float(s)
    except:
        return None

def _sum_costs(parts: Dict[str, Optional[float]]) -> Optional[float]:
    values = [parts.get(k) for k in ["part_cost", "fitting_cost", "dainting_cost", "paint_cost", "other_cost"] if isinstance(parts.get(k), (int, float))]
    return float(sum(values)) if values else None

KB_BUCKET = os.getenv("KB_BUCKET", "automotive-damage-processing-sources3bucket-zc1cdw6k30o1")
KB_KEY = os.getenv("KB_KEY", "car_bills.csv")

def load_kb_s3(bucket: str = KB_BUCKET, key: str = KB_KEY):
    global KB_ROWS, KB_MAP, KB_COMPONENTS_BY_BMR

    s3 = boto3.client("s3")
    try:
        obj = s3.get_object(Bucket=bucket, Key=key)
        df = pd.read_csv(io.BytesIO(obj['Body'].read()))
    except Exception as e:
        print(f"[KB] Failed to read from S3 {bucket}/{key}: {e}")
        KB_ROWS = pd.DataFrame(columns=["brand", "model", "region", "component",
                                        "part_cost", "fitting_cost", "dainting_cost",
                                        "paint_cost", "other_cost"])
        KB_MAP = {}
        KB_COMPONENTS_BY_BMR = {}
        return

    KB_ROWS = df.copy()
    KB_MAP.clear()
    KB_COMPONENTS_BY_BMR.clear()
    for _, row in KB_ROWS.iterrows():
        brand, model, region, component = _norm(row["brand"]), _norm(row["model"]), _norm(row["region"]), _norm(row["component"])
        key = (_norm_key(brand), _norm_key(model), _norm_key(region), _norm_key(component))
        KB_MAP[key] = {
            "brand": brand,
            "model": model,
            "region": region,
            "component": component,
            "part_cost": _parse_cost(row.get("part_cost")),
            "fitting_cost": _parse_cost(row.get("fitting_cost")),
            "dainting_cost": _parse_cost(row.get("dainting_cost")),
            "paint_cost": _parse_cost(row.get("paint_cost")),
            "other_cost": _parse_cost(row.get("other_cost")),
        }
        bmr = (_norm_key(brand), _norm_key(model), _norm_key(region))
        KB_COMPONENTS_BY_BMR.setdefault(bmr, []).append(component)

    print(f"[KB] Loaded {len(KB_MAP)} rows from S3 {bucket}/{key}")

print("[DEBUG] Loading KB from S3...")
print(f"[DEBUG] Using S3 KB: bucket={KB_BUCKET}, key={KB_KEY}")
load_kb_s3()  
print(f"[DEBUG] KB_ROWS shape: {KB_ROWS.shape}")
print(f"[DEBUG] KB_MAP keys sample: {list(KB_MAP.keys())[:5]}")
print(f"[DEBUG] KB_COMPONENTS_BY_BMR keys sample: {list(KB_COMPONENTS_BY_BMR.keys())[:5]}")

def normalize_component_name(name: str, kb_components: List[str]) -> str:
    raw_norm = _norm_key(name)
    for syn, kb_std in COMPONENT_SYNONYMS.items():
        if _norm_key(syn) == raw_norm:
            return kb_std
    kb_norm_map = {_norm_key(c): c for c in kb_components}
    match = get_close_matches(raw_norm, kb_norm_map.keys(), n=1, cutoff=0.6)
    return kb_norm_map[match[0]] if match else name

def ai_generate_description_natural(component: str, damage_context: str = "") -> str:
    system_prompt = (
        "You are an expert car damage inspector. "
        f"Write a detailed, 1-line sentence describing visible damage for this component: {component}. "
        "Dont include the component name like - The front bumper has, The rear bumper has, The back panel has, The right tail light has, etc"
        "Include the type of damage (dent, scratch, crack, broken, paint chipped, etc.), "
        "location on the component (left, right, top, bottom, corner, etc.), "
        "and severity (minor, deep, shattered, etc.) if available. "
        "Do NOT mention other components. Do NOT say 'not applicable' or similar. "
        "Make each description unique for the component."
    )

    user_prompt = f"Component: {component}. Context: {damage_context}."

    body = {
        "anthropic_version": "bedrock-2023-05-31",
        "system": system_prompt,
        "messages": [{"role": "user", "content": user_prompt}],
        "temperature": 0.3, 
        "max_tokens": 80
    }

    try:
        resp = bedrock_client.invoke_model(
            modelId=MODEL_TEXT,
            contentType="application/json",
            accept="application/json",
            body=json.dumps(body).encode("utf-8")
        )
        result = json.loads(resp["body"].read())
        text = result["content"][0]["text"].strip()
        if any(x in text.lower() for x in ["not applicable", "general damage"]):
            text = f"{component} shows visible damage with dents or scratches."
        return text
    except Exception as e:
        print("[AI DESC] Error:", e)
        return f"{component} shows visible damage."

def normalize_component_for_kb(component: str, brand: str, model: str, region: str) -> str:
    bmr = (_norm_key(brand), _norm_key(model), _norm_key(region))
    kb_components = KB_COMPONENTS_BY_BMR.get(bmr)
    if not kb_components:
        return component  
    return normalize_component_name(component, kb_components)

def kb_lookup(brand: str, model: str, region: str, component: str) -> Optional[Dict[str, Any]]:
    key = (_norm_key(brand), _norm_key(model), _norm_key(region), _norm_key(component))
    if key in KB_MAP:
        return KB_MAP[key]
    candidates = [comp for (_b, _m, _r, comp) in KB_MAP.keys() if _b == _norm_key(brand) and _m == _norm_key(model) and _r == _norm_key(region)]
    match = get_close_matches(_norm_key(component), [_norm_key(c) for c in candidates], n=1, cutoff=0.5)
    if match:
        for (_b, _m, _r, comp) in KB_MAP.keys():
            if _b == _norm_key(brand) and _m == _norm_key(model) and _r == _norm_key(region) and _norm_key(comp) == match[0]:
                return KB_MAP[(_b, _m, _r, comp)]
    return None

def compress_image(file, max_size_kb=5000) -> str:
    image = Image.open(file)
    if image.mode in ("RGBA", "P"):
        image = image.convert("RGB")
    max_width = 1024
    if image.width > max_width:
        ratio = max_width / float(image.width)
        new_height = int(image.height * ratio)
        image = image.resize((max_width, new_height), Image.LANCZOS)
    buffer = io.BytesIO()
    image.save(buffer, format="JPEG", optimize=True, quality=85)
    size_kb = buffer.getbuffer().nbytes / 1024
    while size_kb > max_size_kb and size_kb > 0:
        buffer = io.BytesIO()
        image.save(buffer, format="JPEG", optimize=True, quality=70)
        size_kb = buffer.getbuffer().nbytes / 1024
    buffer.seek(0)
    return base64.b64encode(buffer.read()).decode()

def analyze_damage_image(encoded_image: str, visible_parts: List[str]) -> dict:
    prompt = f"""
    You are an expert car damage AI.
    The image shows the following components: {visible_parts}.
    Check each of these parts carefully and mark as "damaged" or "ok".
    Respond STRICTLY in JSON:
    {{
        "brand": "...",
        "model": "...",
        "region": "...",
        "parts_status": {{ part: "damaged/ok" for each visible part }},
        "summary": "A short description of observed damages"
    }}
    """

    invoke_body = {
        "anthropic_version": "bedrock-2023-05-31",
        "max_tokens": 1024,
        "temperature": 0.0,  
        "messages": [
            {
                "role": "user",
                "content": [
                    {
                        "type": "image",
                        "source": {
                            "type": "base64",
                            "media_type": "image/png",
                            "data": encoded_image
                        }
                    },
                    {"type": "text", "text": prompt}
                ]
            }
        ]
    }

    body = json.dumps(invoke_body).encode("utf-8")
    response = bedrock_client.invoke_model(
        body=body,
        contentType="application/json",
        accept="application/json",
        modelId=MODEL_IMAGE
    )

    result = json.loads(response["body"].read())
    try:
        data = json.loads(result["content"][0]["text"])
        parts_status = data.get("parts_status", {})
        visible_damage = [p for p, status in parts_status.items() if status == "damaged"]
        data["visible_damage"] = visible_damage
        return data
    except Exception as e:
        print("Failed to parse Claude response:", e, result["content"][0]["text"])
        return {
            "brand": "unknown",
            "model": "unknown",
            "region": "unknown",
            "parts_status": {p: "unknown" for p in [
                "Dickey Panel", "Bumper Front", "Bumper Rear", "Bumper Holder Rear",
                "Back Panel", "Dickey Glass", "Tail Light", "Dickey Lock",
                "Bonnet Hood", "Bonnet Hinges", "Headlight", "Member Hoodlock", "Upper Grill Bump"
            ]},
            "visible_damage": [],
            "summary": ""
        }

def merge_summaries(prompt_text):
    body = {
        "anthropic_version": "bedrock-2023-05-31",
        "messages": [{"role": "user", "content": prompt_text}],
        "temperature": 0.5,
        "max_tokens": 1024
    }
    response = bedrock_client.invoke_model(
        modelId=MODEL_TEXT,
        contentType="application/json",
        accept="application/json",
        body=json.dumps(body).encode("utf-8")
    )
    result = json.loads(response["body"].read())
    return result["content"][0]["text"].strip()

def detect_visible_parts(encoded_image: str) -> List[str]:
    prompt = """
    You are an expert car damage AI.
    Look at the uploaded image and detect which car components are actually visible from this list:
    ["Dickey Panel", "Bumper Front", "Bumper Rear", "Bumper Holder Rear", "Back Panel",
     "Dickey Glass", "Tail Light", "Dickey Lock", "Bonnet Hood", "Bonnet Hinges",
     "Headlight", "Member Hoodlock", "Upper Grill Bump"]
    Return STRICT JSON: {"visible_parts": [ ... ]}
    Only include parts you can actually see.
    """
    body = {
        "anthropic_version": "bedrock-2023-05-31",
        "max_tokens": 512,
        "temperature": 0.0,
        "messages": [
            {"role": "user",
             "content": [
                 {"type": "image", "source": {"type": "base64", "media_type": "image/png", "data": encoded_image}},
                 {"type": "text", "text": prompt}
             ]}
        ]
    }
    resp = bedrock_client.invoke_model(
        modelId=MODEL_IMAGE,
        contentType="application/json",
        accept="application/json",
        body=json.dumps(body).encode("utf-8")
    )
    result = json.loads(resp["body"].read())
    try:
        data = json.loads(result["content"][0]["text"])
        return data.get("visible_parts", [])
    except Exception:
        return []

def ai_map_components(
    damages: List[str],
    brand: str,
    model: str,
    region: str,
    kb_components_for_bmr: List[str]
) -> List[Dict[str, str]]:
    """
    Returns list of {"detected": <raw>, "standard": <standard_component>}
    """
    system_prompt = (
        "You are a strict JSON generator that maps raw damage phrases to standardized component names.\n"
        "Output ONLY JSON. No explanations.\n"
        "Prefer picking from the provided 'candidate_components' list. If none is suitable, guess a common automotive component name.\n"
        "Schema:\n"
        "{\n"
        '  "matched_components": [\n'
        '    {"detected":"...","standard":"..."}\n'
        "  ]\n"
        "}\n"
    )
    user_prompt = {
        "brand": brand, "model": model, "region": region,
        "detected_damages": damages,
        "candidate_components": kb_components_for_bmr
    }

    body = {
        "anthropic_version": "bedrock-2023-05-31",
        "system": system_prompt,
        "messages": [{"role": "user", "content": json.dumps(user_prompt)}],
        "temperature": 0.0,
        "max_tokens": 800
    }

    response = bedrock_client.invoke_model(
        modelId=MODEL_TEXT,
        contentType="application/json",
        accept="application/json",
        body=json.dumps(body).encode("utf-8")
    )
    result = json.loads(response["body"].read())
    text = result["content"][0]["text"]

    try:
        data = json.loads(text)
        out = data.get("matched_components", [])
        if not isinstance(out, list):
            return []
        cleaned = []
        for it in out:
            det = _norm(it.get("detected"))
            std = _norm(it.get("standard"))
            if det:
                cleaned.append({"detected": det, "standard": std or det})
        return cleaned
    except Exception as e:
        print("[AI MAP] Failed to parse JSON:", e, text)
        return []

def ai_estimate_component_cost(
    component: str,
    brand: str,
    model: str,
    region: str,
    context_damage: Optional[str] = None
) -> Optional[float]:
    """
    Ask Claude ONLY for a single component's cost (INR), deterministic.
    """
    system_prompt = (
    "You estimate Indian automotive repair costs in INR. "
    "Return ONLY JSON with schema: {\"cost\": <number>} with no extra text. "
    "Be conservative and realistic. Include all relevant charges (part + fitting + painting) in the single number. "
    "Do NOT return separate labour or paint costs."
)

    user_payload = {
        "brand": brand, "model": model, "region": region,
        "component": component,
        "damage_context": context_damage
    }
    body = {
        "anthropic_version": "bedrock-2023-05-31",
        "system": system_prompt,
        "messages": [{"role": "user", "content": json.dumps(user_payload)}],
        "temperature": 0.0,
        "max_tokens": 100
    }
    response = bedrock_client.invoke_model(
        modelId=MODEL_TEXT,
        contentType="application/json",
        accept="application/json",
        body=json.dumps(body).encode("utf-8")
    )
    result = json.loads(response["body"].read())
    text = result["content"][0]["text"]
    try:
        data = json.loads(text)
        cost = data.get("cost", None)
        return float(cost) if cost is not None else None
    except Exception as e:
        print("[AI COST] Failed to parse:", e, text)
        return None

@app.post("/analyze")
async def analyze(images: List[UploadFile] = File(...), meta: str = Form(...)):
    extra = json.loads(meta)
    all_metadata = []
    combined_damages = []
    brand, model = "unknown", "unknown"

    print(f"[DEBUG] Received {len(images)} images, meta={extra}")

    exhaustive_parts = [
        "Dickey Panel", "Bumper Front", "Bumper Rear", "Bumper Holder Rear",
        "Back Panel", "Dickey Glass", "Tail Light", "Dickey Lock",
        "Bonnet Hood", "Bonnet Hinges", "Headlight", "Member Hoodlock", "Upper Grill Bump"
    ]
    parts_str = ', '.join(exhaustive_parts)

    for idx, image in enumerate(images, start=1):
        encoded_image = compress_image(image.file)
        visible_parts = detect_visible_parts(encoded_image)

        prompt = f"""
            You are an expert car damage AI. The uploaded image may contain multiple damaged components. 
            Check CAREFULLY for ALL damages, including small or partially obscured parts.
            Use this list of parts to guide you: {parts_str}.
            If you see damage to any of these parts, mark it in 'visible_damage'.
            Respond STRICTLY in JSON:
            {{
            "brand": "...",
            "model": "...",
            "region": "...",
            "visible_damage": [...],
            "summary": "A concise description of all observed damages."
            }}
            Do NOT omit any part from the list even if damage is minor or partially visible.
            Respond ONLY with JSON.
            """

        metadata = analyze_damage_image(encoded_image, visible_parts)
        all_metadata.append(metadata)

        print(f"[DEBUG] Image {idx}: metadata returned from Claude:")
        print(json.dumps(metadata, indent=2))

        vd = metadata.get("visible_damage")
        if isinstance(vd, list):
            for x in vd:
                if isinstance(x, str):
                    combined_damages.append(x)
                    print(f"[DEBUG] Image {idx}: added visible damage string: {x}")
                elif isinstance(x, dict):
                    txt = x.get("panel") or x.get("part") or x.get("area") or x.get("desc") or x.get("severity") or ""
                    if txt:
                        combined_damages.append(str(txt))
                        print(f"[DEBUG] Image {idx}: added visible damage dict value: {txt}")

        if brand == "unknown" and metadata.get("brand", "unknown") != "unknown":
            brand = metadata["brand"]
            print(f"[DEBUG] Brand detected: {brand}")
        if model == "unknown" and metadata.get("model", "unknown") != "unknown":
            model = metadata["model"]
            print(f"[DEBUG] Model detected: {model}")

    image_summaries = [m.get("summary", "") for m in all_metadata if m.get("summary")]
    print(f"[DEBUG] Collected image summaries: {image_summaries}")

    merge_prompt = f"""
        You are a car damage expert. The following are separate descriptions of damages for multiple photos of the same car.
        Combine them into one concise paragraph that describes ALL damages naturally, including minor ones like Dickey/Trunk.
        Do NOT start with phrases like 'Based on the descriptions provided'. 
        Just describe the car and its damages clearly in plain language:

        {chr(10).join(image_summaries)}
        """

    damage_summary_merged = merge_summaries(merge_prompt)
    print(f"[DEBUG] Merged damage summary:\n{damage_summary_merged}")

    is_car = any(
        (m.get("brand") != "unknown" or m.get("model") != "unknown" or m.get("visible_damage"))
        for m in all_metadata
    )
    print(f"[DEBUG] isCar={is_car}")
    print(f"[DEBUG] Combined visible_damage={combined_damages}")

    return {
        "isCar": is_car,
        "regionAvailable": True,
        "brand": brand,
        "model": model,
        "damageSummary": damage_summary_merged,
        "visible_damage": combined_damages,
        "brandEditable": brand == "unknown",
        "modelEditable": model == "unknown"
    }

@app.post("/send-email")
async def send_email(
    to: str = Form(...),
    subject: str = Form(...),
    body: str = Form(...),
    images: List[UploadFile] = File(None) 
):
    ses = boto3.client("ses", region_name="us-west-2")
    from_email = "dhruv.chowdary@neenopal.com"

    msg = MIMEMultipart('mixed')
    msg['Subject'] = subject
    msg['From'] = from_email
    msg['To'] = to

    image_html = ""
    if images:
        for idx, image in enumerate(images):
            image_bytes = await image.read()
            content_id = f"uploadedImage{idx}"

            att = MIMEApplication(image_bytes)
            att.add_header('Content-ID', f'<{content_id}>')
            att.add_header(
                'Content-Disposition',
                'inline',
                filename=os.path.basename(image.filename)
            )
            msg.attach(att)

            image_html += f'<img src="cid:{content_id}" width="400"><br>'

        if 'id="vehicle-info-marker"' in body:
            body = body.replace(
                '<h3 id="vehicle-info-marker">Vehicle Information</h3>',
                f'<h3 id="vehicle-info-marker">Vehicle Information</h3>{image_html}',
                1
            )
        else:
            body += image_html

    msg_body = MIMEMultipart('alternative')
    htmlpart = MIMEText(body, 'html', 'utf-8')
    msg_body.attach(htmlpart)
    msg.attach(msg_body)

    try:
        response = ses.send_raw_email(
            Source=from_email,
            Destinations=[to],
            RawMessage={'Data': msg.as_string()}
        )
        return {"success": True, "messageId": response["MessageId"]}
    except Exception as e:
        return {"success": False, "error": str(e)}

@app.post("/estimate")
async def estimate(payload: dict):
    brand    = payload.get("brand") or payload.get("vehicle", {}).get("make") or "unknown"
    model    = payload.get("model") or payload.get("vehicle", {}).get("model") or "unknown"
    location = payload.get("location") or "unknown"

    damage_phrases: list[str] = []
    if isinstance(payload.get("visible_damage"), list):
        for x in payload["visible_damage"]:
            if isinstance(x, str):
                damage_phrases.append(x)
            elif isinstance(x, dict):
                txt = x.get("panel") or x.get("part") or x.get("desc") or x.get("severity") or ""
                if txt:
                    damage_phrases.append(str(txt))
    if not damage_phrases and isinstance(payload.get("damages"), list):
        for d in payload["damages"]:
            s = d.get("severity") if isinstance(d, dict) else ""
            if s:
                damage_phrases.append(str(s))
    if not damage_phrases:
        damage_phrases = [payload.get("damageSummary", "general collision damage")]

    damage_phrases = list(dict.fromkeys(damage_phrases))

    is_india = True
    try:
        is_india_prompt = f"""
        You are a smart assistant. I will give you a location string.
        Tell me if this location is in India.
        Respond strictly in JSON: {{"isIndia": true}} or {{"isIndia": false}}.
        Location: "{location}"
        """
        body_is_india = {
            "anthropic_version": "bedrock-2023-05-31",
            "messages": [{"role": "user", "content": is_india_prompt}],
            "temperature": 0.0,
            "max_tokens": 50
        }
        resp = bedrock_client.invoke_model(
            modelId=MODEL_TEXT,
            contentType="application/json",
            accept="application/json",
            body=json.dumps(body_is_india).encode("utf-8")
        )
        result = json.loads(resp["body"].read())
        text_output = result["content"][0]["text"]
        is_india_json = json.loads(text_output)
        is_india = bool(is_india_json.get("isIndia", False))
    except Exception as e:
        print("Failed to parse isIndia:", e)

    kb_components_for_bmr = KB_COMPONENTS_BY_BMR.get((_norm_key(brand), _norm_key(model), _norm_key(location)), [])

    mappings = ai_map_components(
        damages=damage_phrases,
        brand=brand, model=model, region=location,
        kb_components_for_bmr=kb_components_for_bmr
    )

    if not mappings:
        mappings = [{"detected": damage_phrases[0], "standard": "General Body Repair"}]

    seen = set()
    cleaned_mappings = []
    for m in mappings:
        std = m["standard"] or m["detected"]
        if std not in seen:
            cleaned_mappings.append(m)
            seen.add(std)
    mappings = cleaned_mappings

    items: list[dict] = []
    notes: list[str] = []
    numeric_total = 0.0
    sno = 1

    for m in mappings:
        detected = m["detected"]
        standard = m["standard"] or detected

        kb_entry = kb_lookup(brand, model, location, standard)
        if kb_entry:
            subcosts = {
                "part_cost": kb_entry.get("part_cost"),
                "fitting_cost": kb_entry.get("fitting_cost"),
                "dainting_cost": kb_entry.get("dainting_cost"),
                "paint_cost": kb_entry.get("paint_cost"),
                "other_cost": kb_entry.get("other_cost"),
            }
            component_total = _sum_costs(subcosts)
            numeric_total += component_total if component_total else 0
            atpar_fields = [k for k, v in subcosts.items() if v is None]
            print(kb_entry['component'], detected)
            desc = ai_generate_description_natural(kb_entry['component'], detected)

            items.append({
                "SNo": sno,
                "Component": kb_entry["component"],
                "Description": desc,
                "Cost (INR)": int(component_total) if component_total else 0,
                "cost_source": "knowledge_base" if not atpar_fields else "knowledge_base_atpar"
            })
            if atpar_fields:
                notes.append(f"{kb_entry['component']}: ATPAR for {', '.join(atpar_fields)} (requires inspection).")
        else:
            est_cost = ai_estimate_component_cost(standard, brand, model, location, detected)
            numeric_total += est_cost if est_cost else 0
            desc = ai_generate_description_natural(detected, standard)

            items.append({
                "SNo": sno,
                "Component": standard,
                "Description": desc,
                "Cost (INR)": int(est_cost) if est_cost else 0,
                "cost_source": "ai_generated" if est_cost else "unavailable"
            })
            if est_cost is None:
                notes.append(f"{standard}: cost unavailable; manual estimate required.")

        sno += 1

    labour_entry = kb_lookup(brand, model, location, "Labour")
    if labour_entry:
        labour_total = _sum_costs(labour_entry)
    else:
        labour_total = ai_estimate_component_cost("Labour", brand, model, location, "General repair labour")
    if labour_total:
        labour_desc = ai_generate_description_natural("General repair", "Labour")
        items.append({
            "SNo": sno,
            "Component": "Labour",
            "Description": labour_desc,
            "Cost (INR)": int(labour_total),
            "cost_source": "knowledge_base" if labour_entry else "ai_generated"
        })
        numeric_total += labour_total

    paragraphs = [
        "Disclaimer: Please note that this particular estimate is based on inputs received. For a more detailed & accurate estimate, please."
    ]
    if notes:
        paragraphs.extend([f"NOTE: {n}" for n in notes])
    if not is_india:
        paragraphs.append("NOTE: This estimate is calculated using India-based repair standards and costs. For locations outside India, the figures are approximate and meant for reference only.")

    return {
        "currency": "₹",
        "items": items,
        "total": int(numeric_total),
        "paragraphs": paragraphs,
        "isIndia": is_india
    }
