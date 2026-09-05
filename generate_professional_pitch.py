"""
generate_professional_pitch.py

Broadcast-Grade Product Pitch Video Generator for LedgerZero:
- Natural, human-like voiceover narration using Microsoft Azure Neural Voice (en-US-AndrewNeural)
- Proper pronunciation for Qwen 2.5 3B (single-syllable "QWEN", /kwɛn/)
- Pure product sign-off in voiceover (Rishikesh P credit purely visual on outro card)
- Sharp vector graphics (zero missing emoji boxes or glyph glitches)
- 1080p 30fps Full HD resolution
- Clean edge-to-edge UI presentation (NO clunky blocking boxes)
- Sleek modern Bottom HUD Capsule (Indicator dot + Tagline + High-contrast subtitle)
- Minimal executive outro card featuring "Created by Rishikesh P" (No localhost/buildathon)
- High-profile H.264 + 44.1kHz AAC stereo audio muxed via PyAV
"""

import os
import shutil
import numpy as np
from PIL import Image, ImageDraw, ImageFont
import av
import asyncio
import edge_tts
from gtts import gTTS

WIDTH = 1920
HEIGHT = 1080
FPS = 30

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
AUDIO_DIR = os.path.join(BASE_DIR, "scratch_neural_audio")
os.makedirs(AUDIO_DIR, exist_ok=True)

FONT_BOLD = r"C:\Windows\Fonts\segoeuib.ttf"
FONT_REG = r"C:\Windows\Fonts\segoeui.ttf"
FONT_SEMIBOLD = r"C:\Windows\Fonts\seguisb.ttf"
FONT_MONO = r"C:\Windows\Fonts\consola.ttf"

def get_font(path, size):
    try:
        return ImageFont.truetype(path, size)
    except Exception:
        return ImageFont.load_default()

font_brand = get_font(FONT_BOLD, 74)
font_title = get_font(FONT_BOLD, 36)
font_subtitle = get_font(FONT_REG, 26)
font_badge = get_font(FONT_BOLD, 15)
font_caption = get_font(FONT_SEMIBOLD, 22)
font_chip = get_font(FONT_BOLD, 15)
font_credits_name = get_font(FONT_BOLD, 22)

async def _synth_edge(text, output_mp3, voice="en-US-AndrewNeural", max_retries=5):
    for attempt in range(1, max_retries + 1):
        try:
            comm = edge_tts.Communicate(text, voice, rate="+0%", pitch="+0Hz")
            await comm.save(output_mp3)
            if os.path.exists(output_mp3) and os.path.getsize(output_mp3) > 1000:
                return True
        except Exception:
            await asyncio.sleep(1.8 * attempt)
    return False

def synthesize_neural_speech(text, output_mp3):
    """Generate authentic human-like voiceover via Azure Neural Andrew voice with fallback."""
    if os.path.exists(output_mp3) and os.path.getsize(output_mp3) > 5000:
        return

    # Try primary natural human voice (Andrew Neural)
    success = asyncio.run(_synth_edge(text, output_mp3, voice="en-US-AndrewNeural"))
    if not success:
        # Secondary natural voice (Christopher Neural)
        success = asyncio.run(_synth_edge(text, output_mp3, voice="en-US-ChristopherNeural"))
    if not success:
        # Ultimate fallback to gTTS
        tts = gTTS(text=text, lang="en", tld="com", slow=False)
        tts.save(output_mp3)

def decode_audio_to_stereo(audio_path, target_rate=44100):
    """Decode MP3 audio and return (duration_sec, 2xN float32 numpy array) with studio normalization."""
    container = av.open(audio_path)
    resampler = av.AudioResampler(format="fltp", layout="stereo", rate=target_rate)

    chunks = []
    for frame in container.decode(audio=0):
        for resampled in resampler.resample(frame):
            chunks.append(resampled.to_ndarray())
    container.close()

    if chunks:
        stereo = np.concatenate(chunks, axis=1)
    else:
        stereo = np.zeros((2, target_rate), dtype=np.float32)

    # Studio peak normalization (-1.0 dBFS)
    peak = np.max(np.abs(stereo))
    if peak > 1e-4:
        stereo = (stereo / peak) * 0.88

    # Smooth 15ms boundary taper to prevent clicks
    taper_len = int(target_rate * 0.015)
    if stereo.shape[1] > taper_len * 2:
        fade_in = np.linspace(0.0, 1.0, taper_len)
        fade_out = np.linspace(1.0, 0.0, taper_len)
        stereo[:, :taper_len] *= fade_in
        stereo[:, -taper_len:] *= fade_out

    duration = stereo.shape[1] / float(target_rate)
    return duration, stereo

def draw_radial_glow(canvas, cx, cy, radius, color):
    glow = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(glow)
    for r in range(radius, 0, -10):
        alpha = int((1.0 - r / radius) ** 2 * color[3])
        draw.ellipse([cx - r, cy - r, cx + r, cy + r], fill=(color[0], color[1], color[2], alpha))
    return Image.alpha_composite(canvas, glow)

def draw_vector_bolt(draw, cx, cy, fill_color=(0, 255, 136)):
    """Draw a razor-sharp vector lightning bolt (no font emoji dependencies)."""
    bolt = [
        (cx + 2, cy - 24),
        (cx + 14, cy - 24),
        (cx + 1, cy - 2),
        (cx + 12, cy - 2),
        (cx - 12, cy + 26),
        (cx - 3, cy + 4),
        (cx - 12, cy + 4)
    ]
    draw.polygon(bolt, fill=fill_color)

def render_cinematic_title_card(t):
    """Render keynote-quality title card with vector emblem and high-contrast chips."""
    base = Image.new("RGBA", (WIDTH, HEIGHT), (6, 9, 16, 255))
    base = draw_radial_glow(base, WIDTH // 2, HEIGHT // 2 - 50, 480, (0, 229, 255, 38))
    base = draw_radial_glow(base, WIDTH // 2, HEIGHT // 2 + 100, 420, (189, 0, 255, 24))

    draw = ImageDraw.Draw(base)
    cx, cy = WIDTH // 2, HEIGHT // 2

    # Emblem box
    emblem_size = 76
    draw.rounded_rectangle([cx - emblem_size//2, cy - 190, cx + emblem_size//2, cy - 190 + emblem_size],
                           radius=20, fill=(12, 20, 34, 255), outline=(0, 229, 255, 220), width=2)
    draw_vector_bolt(draw, cx, cy - 152, (0, 255, 136))

    # Brand Title
    brand_text = "LEDGERZERO"
    bb = font_brand.getbbox(brand_text)
    tw = bb[2] - bb[0]
    draw.text((cx - tw // 2, cy - 85), brand_text, fill=(255, 255, 255), font=font_brand)

    # Subtitle
    sub_text = "Autonomous Corporate Treasury & Multi-Source Reconciliation"
    sb = font_subtitle.getbbox(sub_text)
    sw = sb[2] - sb[0]
    draw.text((cx - sw // 2, cy + 18), sub_text, fill=(160, 185, 220), font=font_subtitle)

    # Category Badge
    track_text = "AUTONOMOUS TREASURY  •  ENTERPRISE RECONCILIATION"
    tb = font_badge.getbbox(track_text)
    tw = tb[2] - tb[0]
    badge_w = tw + 48
    draw.rounded_rectangle([cx - badge_w//2, cy + 76, cx + badge_w//2, cy + 118],
                           radius=21, fill=(10, 18, 30, 255), outline=(0, 229, 255, 180), width=1)
    draw.text((cx - tw // 2, cy + 86), track_text, fill=(0, 229, 255), font=font_badge)

    # Capability Chips
    chips = [
        ("100% Precision Ground Truth", (0, 255, 136)),
        ("Zero-Dependency Core", (0, 229, 255)),
        ("NVIDIA GPU Accelerated", (189, 0, 255)),
        ("Closed-Loop SLAs", (255, 170, 0)),
    ]

    total_w = 0
    chip_widths = []
    for text, col in chips:
        cb = font_chip.getbbox(text)
        w = (cb[2] - cb[0]) + 44
        chip_widths.append(w)
        total_w += w
    total_w += (len(chips) - 1) * 16

    start_x = cx - total_w // 2
    for (text, col), cw in zip(chips, chip_widths):
        draw.rounded_rectangle([start_x, cy + 148, start_x + cw, cy + 188],
                               radius=12, fill=(12, 18, 30, 255), outline=(col[0], col[1], col[2], 180), width=1)
        draw.ellipse([start_x + 14, cy + 164, start_x + 22, cy + 172], fill=col)
        draw.text((start_x + 30, cy + 158), text, fill=(235, 242, 255), font=font_chip)
        start_x += cw + 16

    return np.array(base.convert("RGB"))

def render_cinematic_outro_card(t):
    """Render minimal, elegant closing verdict card with Created by Rishikesh P."""
    base = Image.new("RGBA", (WIDTH, HEIGHT), (6, 9, 16, 255))
    base = draw_radial_glow(base, WIDTH // 2, HEIGHT // 2 - 30, 520, (0, 255, 136, 32))
    base = draw_radial_glow(base, WIDTH // 2, HEIGHT // 2 + 80, 420, (0, 229, 255, 26))

    draw = ImageDraw.Draw(base)
    cx, cy = WIDTH // 2, HEIGHT // 2

    # Emblem box
    emblem_size = 76
    draw.rounded_rectangle([cx - emblem_size//2, cy - 170, cx + emblem_size//2, cy - 170 + emblem_size],
                           radius=20, fill=(10, 18, 32, 255), outline=(0, 255, 136, 220), width=2)
    draw_vector_bolt(draw, cx, cy - 132, (0, 255, 136))

    # Big Brand Title
    brand_text = "LEDGERZERO"
    bb = font_brand.getbbox(brand_text)
    tw = bb[2] - bb[0]
    draw.text((cx - tw // 2, cy - 65), brand_text, fill=(255, 255, 255), font=font_brand)

    # Tagline
    sub_text = "Truth Over Throughput. Production Ready."
    sb = font_subtitle.getbbox(sub_text)
    sw = sb[2] - sb[0]
    draw.text((cx - sw // 2, cy + 35), sub_text, fill=(0, 255, 136), font=font_subtitle)

    # End Credits Badge: Created by Rishikesh P
    credit_text = "Created by Rishikesh P"
    cb = font_credits_name.getbbox(credit_text)
    cw = cb[2] - cb[0]
    badge_w = cw + 60
    badge_h = 52
    bx = cx - badge_w // 2
    by = cy + 120

    draw.rounded_rectangle([bx, by, bx + badge_w, by + badge_h],
                           radius=26, fill=(10, 16, 28, 255), outline=(0, 229, 255, 180), width=1)
    draw.ellipse([bx + 20, by + 22, bx + 28, by + 30], fill=(0, 229, 255))
    draw.text((bx + 38, by + 13), credit_text, fill=(240, 246, 255), font=font_credits_name)

    return np.array(base.convert("RGB"))

def render_product_frame(img_source, zoom, pan_x, pan_y, pill_text, pill_color, subtitle_text):
    """
    Renders clean edge-to-edge application view with:
    - Subtle smooth camera motion (Ken Burns zoom / pan)
    - Full unobstructed view of the top brand header
    - Sleek modern Bottom HUD Capsule (Category Dot + Pill + Subtitle)
    """
    base = Image.new("RGBA", (WIDTH, HEIGHT), (0, 0, 0, 255))

    if img_source is not None:
        iw, ih = img_source.size
        aspect = WIDTH / HEIGHT
        target_h = ih / zoom
        target_w = target_h * aspect
        if target_w > iw:
            target_w = iw / zoom
            target_h = target_w / aspect

        max_pan_x = max(0, iw - target_w)
        max_pan_y = max(0, ih - target_h)

        cx = pan_x * max_pan_x
        cy = pan_y * max_pan_y

        cropped = img_source.crop((cx, cy, cx + target_w, cy + target_h))
        resized = cropped.resize((WIDTH, HEIGHT), Image.Resampling.LANCZOS)
        base.paste(resized, (0, 0))

    overlay = Image.new("RGBA", (WIDTH, HEIGHT), (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)

    # Clean Bottom HUD Capsule
    if pill_text or subtitle_text:
        bb_badge = font_badge.getbbox(pill_text) if pill_text else (0, 0, 0, 0)
        w_badge = bb_badge[2] - bb_badge[0]

        bb_sub = font_caption.getbbox(subtitle_text) if subtitle_text else (0, 0, 0, 0)
        w_sub = bb_sub[2] - bb_sub[0]

        card_w = max(w_badge + 70, w_sub + 60)
        card_w = min(card_w, WIDTH - 120)
        card_h = 76
        center_x = WIDTH // 2
        card_x = center_x - card_w // 2
        card_y = HEIGHT - card_h - 32

        # Translucent glass capsule
        draw.rounded_rectangle([card_x, card_y, card_x + card_w, card_y + card_h],
                               radius=18, fill=(8, 12, 22, 235), outline=(255, 255, 255, 45), width=1)

        # Top Badge Line (Dot + Uppercase Tag)
        if pill_text:
            badge_start_x = center_x - (w_badge + 20) // 2
            draw.ellipse([badge_start_x, card_y + 14, badge_start_x + 8, card_y + 22], fill=pill_color)
            draw.text((badge_start_x + 16, card_y + 10), pill_text, fill=pill_color, font=font_badge)

        # Bottom Subtitle Line (High-contrast white)
        if subtitle_text:
            draw.text((center_x - w_sub // 2, card_y + 38), subtitle_text, fill=(245, 248, 255), font=font_caption)

    final = Image.alpha_composite(base, overlay)
    return np.array(final.convert("RGB"))

def main():
    print("=" * 75)
    print("LEDGERZERO — BROADCAST PITCH VIDEO GENERATOR (AZURE NEURAL TTS)")
    print("=" * 75)

    # Scene definitions with natural conversational prosody, accurate phonetics, and no buildathon mentions
    scenes = [
        {
            "type": "title",
            "script": "Corporate finance teams lose weeks every month, manually matching bank statements against ERP ledgers. Meet LedgerZero... an autonomous, truth-first corporate treasury and automated reconciliation platform.",
            "pill": "AUTONOMOUS CORPORATE TREASURY",
            "pill_color": (0, 229, 255),
            "sub": "Autonomous Corporate Treasury & Multi-Source Reconciliation Agent"
        },
        {
            "type": "product",
            "img": os.path.join(BASE_DIR, "dashboard.html"), # Fallback reference
            "script": "LedgerZero ingests PDF, Excel, Word, CSV, and XML statements with automatic schema mapping. It reconciles multi-source enterprise feeds, with 100 percent precision on verified ground truth.",
            "pill": "100.0% PRECISION GROUND TRUTH  •  MULTI-FORMAT INGESTION",
            "pill_color": (0, 255, 136),
            "sub": "Multi-Format Statement Ingestion (PDF, XLSX, CSV, XML) • 100% Precision on Ground Truth",
            "zoom_start": 1.0, "zoom_end": 1.05, "pan_x": 0.0, "pan_y_start": 0.0, "pan_y_end": 0.08
        },
        {
            "type": "product",
            "script": "Rather than relying on black-box matchers that hallucinate pairs, LedgerZero enforces truth over throughput. Transactions flow through Exact, Fuzzy, and Split settlements, escalating edge cases to local GPU reasoning.",
            "pill": "5-STAGE PROGRESSIVE FUNNEL  •  TRUTH OVER THROUGHPUT",
            "pill_color": (0, 229, 255),
            "sub": "5 Deterministic Tiers: Exact, Fuzzy, Split, and GPU LLM • Zero Silent Force-Matching",
            "zoom_start": 1.0, "zoom_end": 1.06, "pan_x": 0.0, "pan_y_start": 0.0, "pan_y_end": 0.12
        },
        {
            "type": "product",
            "script": "Every unresolved exception is automatically turned into an actionable close worklist, with accountable owners, priority SLAs, financial exposure, and one-click adjusting journal entries.",
            "pill": "CLOSED-LOOP CONTROLLER WORKLIST  •  ACTIONABLE SLAS",
            "pill_color": (255, 170, 0),
            "sub": "Closed-Loop Controller Worklist • Accountability, SLAs & 1-Click Adjusting Journal Entries",
            "zoom_start": 1.0, "zoom_end": 1.06, "pan_x": 0.0, "pan_y_start": 0.0, "pan_y_end": 0.14
        },
        {
            "type": "product",
            "script": "Controllers can converse directly with their financial records, using our local Quen 2.5, 3B model. Ask about unlogged charges or timing drift, and receive instant answers, backed by verifiable audit citations.",
            "pill": "SETTLEMENT Q&A COPILOT  •  QWEN 2.5-3B LOCAL LLM",
            "pill_color": (189, 0, 255),
            "sub": "Conversational Settlement Inquiries with Exact Ledger & Bank Audit Citations",
            "zoom_start": 1.0, "zoom_end": 1.05, "pan_x": 0.0, "pan_y_start": 0.0, "pan_y_end": 0.10
        },
        {
            "type": "product",
            "script": "Audited reconciliation directly powers predictive liquidity. The cash forecaster models clearing velocity and pending accruals, projecting cash trajectories across seven, fourteen, and thirty days, while alerting on safety buffer deficits.",
            "pill": "FORWARD CASH FORECASTER  •  LIQUIDITY RISK WARNING",
            "pill_color": (0, 229, 255),
            "sub": "Quantitative Liquidity Trajectory Modeling (7D, 14D, 30D) • Safety-Buffer Deficit Alerts",
            "zoom_start": 1.0, "zoom_end": 1.05, "pan_x": 0.0, "pan_y_start": 0.0, "pan_y_end": 0.10
        },
        {
            "type": "product",
            "script": "Our statutory withholding engine audits invoice line items against Indian tax compliance, reconciling TDS Sections 194C, 194J, and 194Q alongside GST slabs, to instantly uncover and flag tax leakage.",
            "pill": "STATUTORY TAX-LINE MATCHER  •  TDS & GST LEAKAGE",
            "pill_color": (0, 255, 136),
            "sub": "Statutory Withholding Engine: TDS (194C/J/Q) & GST Slabs • Detects Tax Leakage",
            "zoom_start": 1.0, "zoom_end": 1.05, "pan_x": 0.0, "pan_y_start": 0.0, "pan_y_end": 0.10
        },
        {
            "type": "product",
            "script": "Engineered for enterprise scale, LedgerZero reconciles over seventeen thousand transactions per second with zero collisions. Automated twenty-seed sweeps prove its reliability is rock solid.",
            "pill": "ENTERPRISE BENCHMARKS  •  17K+ TXNS/SEC (SUB-60MS)",
            "pill_color": (0, 255, 136),
            "sub": "High-Throughput Suite: 17,263 txns/sec • 57ms Latency • 100% Precision • 20-Seed Verified",
            "zoom_start": 1.0, "zoom_end": 1.05, "pan_x": 0.0, "pan_y_start": 0.0, "pan_y_end": 0.10
        },
        {
            "type": "outro",
            "script": "LedgerZero: Zero discrepancies. Zero black-box hallucinations. Zero-dependency core. And zero close drift. Truth over throughput.",
            "pill": "CREATED BY RISHIKESH P",
            "pill_color": (0, 229, 255),
            "sub": "LedgerZero: Truth Over Throughput • Created by Rishikesh P"
        }
    ]

    # Step 1: Synthesize all speech audio clips using Azure Neural Voice
    print("\n[STEP 1/4] Generating natural human voiceover with conversational pauses...")
    total_audio_samples = []

    for idx, s in enumerate(scenes, start=1):
        mp3_file = os.path.join(AUDIO_DIR, f"scene_{idx}.mp3")
        print(f"  Synthesizing Scene {idx}: {s['pill']}...")
        synthesize_neural_speech(s["script"], mp3_file)
        duration, samples = decode_audio_to_stereo(mp3_file, target_rate=44100)

        # Pad audio slightly (0.28s breathing room at start, 0.38s at end)
        pad_start = np.zeros((2, int(44100 * 0.28)), dtype=np.float32)
        pad_end = np.zeros((2, int(44100 * 0.38)), dtype=np.float32)
        full_samples = np.hstack((pad_start, samples, pad_end))
        scene_duration = full_samples.shape[1] / 44100.0

        s["duration_sec"] = scene_duration
        s["samples"] = full_samples
        total_audio_samples.append(full_samples)
        print(f"    Scene {idx} Natural Voiceover Duration: {scene_duration:.2f}s")

    master_audio = np.hstack(total_audio_samples)
    total_duration_sec = master_audio.shape[1] / 44100.0
    total_frames = int(total_duration_sec * FPS)

    print(f"\n[SUMMARY] Master Audio Duration: {total_duration_sec:.2f}s ({total_frames} video frames @ {FPS} fps)")

    output_mp4 = os.path.join(BASE_DIR, "pitch_video.mp4")
    print(f"\n[STEP 2/4] Initializing H.264 / AAC MP4 Container: {output_mp4}")

    container = av.open(output_mp4, mode="w")

    v_stream = container.add_stream("h264", rate=FPS)
    v_stream.width = WIDTH
    v_stream.height = HEIGHT
    v_stream.pix_fmt = "yuv420p"
    v_stream.options = {"crf": "18", "preset": "fast"}

    a_stream = container.add_stream("aac", rate=44100)
    a_stream.layout = "stereo"
    a_stream.bit_rate = 192000

    print("\n[STEP 3/4] Rendering video frames with dynamic motion and vector graphics...")
    global_frame = 0

    for s_idx, s in enumerate(scenes, start=1):
        scene_frames = int(s["duration_sec"] * FPS)
        print(f"  Rendering Scene {s_idx}/{len(scenes)}: {s['pill']} ({scene_frames} frames)...")

        img_loaded = None
        if s["type"] == "product":
            img_path = s.get("img", "")
            if os.path.exists(img_path):
                try:
                    img_loaded = Image.open(img_path).convert("RGBA")
                except Exception:
                    img_loaded = None

        for f_idx in range(scene_frames):
            global_frame += 1
            t = f_idx / float(max(1, scene_frames - 1))

            if s["type"] == "title":
                frame_rgb = render_cinematic_title_card(t)
            elif s["type"] == "outro":
                frame_rgb = render_cinematic_outro_card(t)
            else:
                zoom = s["zoom_start"] + (s["zoom_end"] - s["zoom_start"]) * t
                pan_y = s["pan_y_start"] + (s["pan_y_end"] - s["pan_y_start"]) * t
                frame_rgb = render_product_frame(
                    img_loaded, zoom, s["pan_x"], pan_y, s["pill"], s["pill_color"], s["sub"]
                )

            # Smooth Crossfade (first 8 frames of each scene after scene 1)
            if f_idx < 8 and s_idx > 1:
                alpha = f_idx / 8.0
                frame_rgb = (frame_rgb * alpha).astype(np.uint8)

            v_frame = av.VideoFrame.from_ndarray(frame_rgb, format="rgb24")
            for packet in v_stream.encode(v_frame):
                container.mux(packet)

    for packet in v_stream.encode():
        container.mux(packet)

    print("\n[STEP 4/4] Muxing synchronized AAC stereo voiceover...")
    chunk_size = 1024
    total_audio_pts = 0

    for i in range(0, master_audio.shape[1], chunk_size):
        chunk = master_audio[:, i:i+chunk_size]
        if chunk.shape[1] < chunk_size:
            pad = np.zeros((2, chunk_size - chunk.shape[1]), dtype=np.float32)
            chunk = np.hstack((chunk, pad))

        a_frame = av.AudioFrame.from_ndarray(chunk, format="fltp", layout="stereo")
        a_frame.sample_rate = 44100
        a_frame.pts = total_audio_pts
        total_audio_pts += chunk_size

        for packet in a_stream.encode(a_frame):
            container.mux(packet)

    for packet in a_stream.encode():
        container.mux(packet)

    container.close()

    size_mb = os.path.getsize(output_mp4) / (1024 * 1024)
    print(f"\n[COMPLETE] Broadcast-Quality Pitch Video Rendered!")
    print(f"  File: {output_mp4}")
    print(f"  Size: {size_mb:.2f} MB")
    print(f"  Audio: 44.1kHz Stereo AAC Natural Human Voiceover (Azure Neural Andrew)")
    print(f"  Video: 1080p H.264 @ {FPS} FPS")

    shutil.rmtree(AUDIO_DIR, ignore_errors=True)

if __name__ == "__main__":
    main()
