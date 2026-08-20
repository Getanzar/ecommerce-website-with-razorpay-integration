import base64
import io
import json
import re

import requests
from django.conf import settings


class AIListingError(Exception):
    pass


def _cloudflare_config():
    account_id = settings.CLOUDFLARE_ACCOUNT_ID.strip()
    api_token = settings.CLOUDFLARE_API_TOKEN.strip()
    if not account_id or not api_token:
        raise AIListingError("AI tools are not configured yet.")
    return account_id, api_token


def _endpoint(model):
    account_id, _ = _cloudflare_config()
    return f"https://api.cloudflare.com/client/v4/accounts/{account_id}/ai/run/{model}"


def _headers():
    _, api_token = _cloudflare_config()
    return {"Authorization": f"Bearer {api_token}"}


def _cloudflare_error(response, action):
    try:
        errors = response.json().get("errors", [])
        detail = errors[0].get("message") if errors else ""
    except (ValueError, AttributeError, IndexError):
        detail = ""
    suffix = f" ({detail})" if detail else ""
    raise AIListingError(f"Cloudflare could not {action} right now.{suffix}")


def _extract_json_object(text):
    text = (text or "").strip()
    text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text, flags=re.IGNORECASE)
    try:
        candidate = json.loads(text)
        if isinstance(candidate, dict) and {"name", "description"} <= candidate.keys():
            return candidate
    except json.JSONDecodeError:
        pass

    decoder = json.JSONDecoder()
    for match in re.finditer(r"\{", text):
        try:
            candidate, _ = decoder.raw_decode(text[match.start():])
        except json.JSONDecodeError:
            continue
        if isinstance(candidate, dict) and {"name", "description"} <= candidate.keys():
            return candidate
    raise AIListingError("Cloudflare returned an unusable listing.")


def generate_listing_copy(product_notes, category, color):
    prompt = (
        "Create an accurate ecommerce listing from the seller's facts. "
        "Never invent materials, certifications, sizes, features, discounts, brand claims, "
        "or guarantees. Return JSON only in this exact shape: "
        '{"name":"...","description":"..."}. '
        "The name must be under 120 characters. The polished description must be useful "
        "and under 900 characters.\n"
        f"Category: {category}\nColor: {color}\nSeller facts: {product_notes}"
    )
    response = requests.post(
        _endpoint(settings.CLOUDFLARE_TEXT_MODEL),
        headers={**_headers(), "Content-Type": "application/json"},
        json={"prompt": prompt, "max_tokens": 500},
        timeout=60,
    )
    if not response.ok:
        _cloudflare_error(response, "generate the listing")
    try:
        payload = response.json()
        result = payload.get("result", payload)
        output_text = result.get("response") or result.get("text")
        listing = _extract_json_object(output_text)
        name = listing["name"].strip()
        description = listing["description"].strip()
        if not name or not description or len(name) > 120 or len(description) > 900:
            raise ValueError
        return {"name": name, "description": description}
    except (ValueError, KeyError, AttributeError) as exc:
        raise AIListingError("Cloudflare returned an unusable listing.") from exc


def _photo_data_uri(uploaded_image):
    uploaded_image.seek(0)
    encoded = base64.b64encode(uploaded_image.read()).decode("ascii")
    uploaded_image.seek(0)
    return f"data:{uploaded_image.content_type};base64,{encoded}"


def _describe_product_photo(uploaded_image, view_name):
    prompt = (
        f"Inspect this {view_name} photograph of a clothing product for an ecommerce listing. "
        "Report only attributes clearly visible in the photograph: garment type, dominant colors, "
        "cut, pattern, closures, pockets, visible construction and design details. Do not guess "
        "fabric composition, brand, gender, age range, size, certifications, or features that cannot "
        "be verified visually. Be concise and factual."
    )
    response = requests.post(
        _endpoint(settings.CLOUDFLARE_VISION_MODEL),
        headers={**_headers(), "Content-Type": "application/json"},
        json={
            "messages": [{"role": "user", "content": prompt}],
            "image": _photo_data_uri(uploaded_image),
            "max_tokens": 350,
            "temperature": 0.1,
        },
        timeout=90,
    )
    if not response.ok:
        _cloudflare_error(response, "inspect the product photo")
    try:
        payload = response.json()
        result = payload.get("result", payload)
        description = result.get("response") if isinstance(result, dict) else result
        if not isinstance(description, str) or not description.strip():
            raise ValueError
        return description.strip()
    except (ValueError, AttributeError) as exc:
        raise AIListingError("Cloudflare returned an unusable photo analysis.") from exc


def generate_listing_from_photos(front_image, back_image, category, seller_notes=""):
    front_description = _describe_product_photo(front_image, "front")
    back_description = _describe_product_photo(back_image, "back")
    notes = (
        f"Front photo observations: {front_description}\n"
        f"Back photo observations: {back_description}\n"
        f"Optional seller facts: {seller_notes or 'None provided'}"
    )
    return generate_listing_copy(notes, category, "Use only visually confirmed colors")


def _image_file_part(uploaded_image):
    """Keep Cloudflare reference images within its 512x512 input limit."""
    uploaded_image.seek(0)
    original = uploaded_image.read()
    try:
        from PIL import Image, ImageOps

        with Image.open(io.BytesIO(original)) as image:
            image = ImageOps.exif_transpose(image)
            image.thumbnail((512, 512))
            if image.mode not in ("RGB", "RGBA"):
                image = image.convert("RGB")
            output = io.BytesIO()
            image.save(output, format="PNG", optimize=True)
            return (uploaded_image.name, output.getvalue(), "image/png")
    except (ImportError, OSError):
        # Validation has already confirmed an image upload. If Pillow is unavailable,
        # let the provider return its normal input error instead of crashing locally.
        return (uploaded_image.name, original, uploaded_image.content_type)


def enhance_product_image(uploaded_image, reference_image=None, view_name="front"):
    files = {"input_image_0": _image_file_part(uploaded_image)}
    if reference_image:
        files["input_image_1"] = _image_file_part(reference_image)
    response = requests.post(
        _endpoint(settings.CLOUDFLARE_IMAGE_MODEL),
        headers=_headers(),
        files=files,
        data={
            "prompt": (
                f"Create a professional ecommerce catalog {view_name} photograph of the exact "
                "product in input image 0; use image 1 only as a consistency reference. Preserve its "
                "colors, shape, texture, markings, proportions, and every identifying detail. "
                "Remove clutter, center the product on a neutral light studio background, add a "
                "realistic soft shadow and clean catalog lighting. Do not add text, logos, props, "
                "accessories, people, or product features that are not in the source image."
            )
        },
        timeout=120,
    )
    if not response.ok:
        _cloudflare_error(response, "enhance the image")

    content_type = response.headers.get("Content-Type", "")
    if content_type.startswith("image/"):
        return base64.b64encode(response.content).decode("ascii")

    try:
        payload = response.json()
        result = payload.get("result", payload)
        encoded = result.get("image") or result.get("b64_json")
        if isinstance(encoded, str) and encoded.startswith("data:image/"):
            encoded = encoded.split(",", 1)[1]
        base64.b64decode(encoded, validate=True)
        return encoded
    except (ValueError, KeyError, TypeError, AttributeError) as exc:
        raise AIListingError("Cloudflare returned an unusable image.") from exc
