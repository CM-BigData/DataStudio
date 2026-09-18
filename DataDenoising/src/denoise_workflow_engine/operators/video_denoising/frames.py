from typing import Any
from denoise_workflow_engine.utilities.video.base import *  # noqa: F403

class KeyFrameExtractOperator(VideoOperator):
    operator_name: str = "key_frame_extract"  # Operator identifier used by workflow configs and the registry.

    def process(self, item: dict) -> dict:
        """Extract key frames from one video sample.

        Business logic:
            1. Skip samples that are missing or lack a decodable video stream.
            2. Use ffmpeg to sample key frames at the configured rate and cap frame count.
            3. Record keyframe paths, counts, and extraction failure issues.

        Args:
                item (dict): Current sample dictionary.

        Returns:
            dict[str, Any]: Updated sample dictionary.

        Examples:
            >>> process
            process
        """
        if self.should_skip(item) or has_any_issue(item, {"video_missing", "decode_failed", "no_video_stream"}):  # Skip keyframe extraction when the video is missing, undecodable, or has no video stream.
            return item
        out_dir = self.run_dir(item, "frames")
        fps = float(self.config.get("sample_fps", 1.0))
        max_frames = int(self.config.get("max_frames", 8))
        pattern = out_dir / "frame_%03d.jpg"
        cmd = [
            ffmpeg_path(),
            "-y",
            "-i",
            str(self.video_path(item)),
            "-vf",
            f"fps={fps}",
            "-frames:v",
            str(max_frames),
            str(pattern),
        ]
        completed = subprocess.run(cmd, capture_output=True, text=True, timeout=int(self.config.get("timeout", 60)))
        frames = sorted(out_dir.glob("frame_*.jpg"))
        item.setdefault("intermediate", {})["keyframe_paths"] = [str(path) for path in frames]
        self.set_metric(item, "keyframe_count", len(frames))
        if completed.returncode != 0 or not frames:  # Flag failure when ffmpeg does not produce frames successfully.
            self.add_issue(item, "keyframe_extract_failed")
        return item

class BlackFrameDetectOperator(VideoOperator):
    operator_name: str = "black_frame_detect"  # Operator identifier used by workflow configs and the registry.

    def process(self, item: dict) -> dict:
        """Detect excessive black frames across sampled key frames.

        Business logic:
            1. Read grayscale thumbnails for each key frame.
            2. Estimate average brightness and black-frame ratio.
            3. Add a black-frame issue when the ratio exceeds the configured threshold.

        Args:
                item (dict): Current sample dictionary.

        Returns:
            dict[str, Any]: Updated sample dictionary.

        Examples:
            >>> process
            process
        """
        frame_paths = item.get("intermediate", {}).get("keyframe_paths", [])
        if not frame_paths:  # Skip frame-level checks when no key frames are available.
            return item
        black_count = 0
        brightness_values = []
        for frame_path in frame_paths:  # Aggregate brightness information frame by frame.
            with Image.open(frame_path) as image:
                gray = image.convert("L").resize((64, 64))
                pixels = list(gray.getdata())
            avg_brightness = mean(pixels)
            brightness_values.append(avg_brightness)
            if avg_brightness < float(self.config.get("black_brightness", 12.0)):  # Count frames whose brightness falls below the configured black-frame threshold.
                black_count += 1
        ratio = black_count / max(len(frame_paths), 1)
        self.set_metric(item, "black_frame_ratio", round(ratio, 4))
        self.set_metric(item, "avg_frame_brightness", round(mean(brightness_values), 4))
        if ratio > float(self.config.get("max_black_frame_ratio", 0.5)):  # Flag the video when black frames dominate.
            self.add_issue(item, "black_frames")
        return item

class VideoBlurDetectOperator(VideoOperator):
    operator_name: str = "video_blur_detect"  # Operator identifier used by workflow configs and the registry.

    def process(self, item: dict) -> dict:
        """Detect blur across sampled video frames.

        Business logic:
            1. Compute sharpness for each sampled frame.
            2. Average sharpness across frames.
            3. Add a blurry-video issue when average sharpness is too low.

        Args:
                item (dict): Current sample dictionary.

        Returns:
            dict[str, Any]: Updated sample dictionary.

        Examples:
            >>> process
            process
        """
        frame_paths = item.get("intermediate", {}).get("keyframe_paths", [])
        if not frame_paths:  # Skip frame-level checks when no key frames are available.
            return item
        sharpness_values = []
        for frame_path in frame_paths:  # Aggregate sharpness information frame by frame.
            with Image.open(frame_path) as image:
                gray = image.convert("L").resize((64, 64))
                pixels = list(gray.getdata())
            sharpness_values.append(frame_sharpness(pixels, 64))
        avg_sharpness = mean(sharpness_values) if sharpness_values else 0.0
        self.set_metric(item, "video_sharpness", round(avg_sharpness, 4))
        if avg_sharpness < float(self.config.get("min_video_sharpness", 3.0)):  # Flag blurry video when sharpness falls below the configured threshold.
            self.add_issue(item, "blurry_video")
        return item

class FrameQualityOperator(VideoOperator):
    operator_name: str = "frame_quality"  # Operator identifier used by workflow configs and the registry.

    def process(self, item: dict) -> dict:
        """Estimate aggregate frame-level quality across sampled frames.

        Business logic:
            1. Measure brightness, variance, and local noise for each frame.
            2. Aggregate per-frame ratios for pure-color, exposure, and noise issues.
            3. Add frame-quality issues when bad-frame ratios exceed configured thresholds.

        Args:
                item (dict): Current sample dictionary.

        Returns:
            dict[str, Any]: Updated sample dictionary.

        Examples:
            >>> process
            process
        """
        frame_paths = item.get("intermediate", {}).get("keyframe_paths", [])
        if not frame_paths:  # Skip frame-level checks when no key frames are available.
            return item
        brightness_values = []
        std_values = []
        noise_values = []
        pure_count = 0
        under_count = 0
        over_count = 0
        high_noise_count = 0
        for frame_path in frame_paths:  # Aggregate quality statistics frame by frame.
            with Image.open(frame_path) as image:
                gray = image.convert("L").resize((96, 96))
                pixels = list(gray.getdata())
            brightness = mean(pixels)
            variance = mean((pixel - brightness) ** 2 for pixel in pixels)
            std = math.sqrt(variance)
            noise = local_noise_score(pixels, 96)
            brightness_values.append(brightness)
            std_values.append(std)
            noise_values.append(noise)
            if std < float(self.config.get("pure_std_threshold", 3.0)):  # Count frames with variance below the pure-frame threshold.
                pure_count += 1
            if brightness < float(self.config.get("min_brightness", 20.0)) and std < float(
                self.config.get("min_exposure_std", 8.0)
            ):
                under_count += 1
            if brightness > float(self.config.get("max_brightness", 245.0)) and std < float(
                self.config.get("min_exposure_std", 8.0)
            ):
                over_count += 1
            if noise > float(self.config.get("max_frame_noise", 24.0)):  # Count frames whose local-noise score exceeds the configured threshold.
                high_noise_count += 1

        total = max(len(frame_paths), 1)
        self.set_metric(item, "frame_avg_brightness", round(mean(brightness_values), 4))
        self.set_metric(item, "frame_avg_std", round(mean(std_values), 4))
        self.set_metric(item, "frame_avg_noise", round(mean(noise_values), 4))
        self.set_metric(item, "pure_frame_ratio", round(pure_count / total, 4))
        self.set_metric(item, "under_exposure_frame_ratio", round(under_count / total, 4))
        self.set_metric(item, "over_exposure_frame_ratio", round(over_count / total, 4))
        self.set_metric(item, "high_noise_frame_ratio", round(high_noise_count / total, 4))
        max_bad_ratio = float(self.config.get("max_bad_frame_ratio", 0.5))
        if pure_count / total > max_bad_ratio:  # Flag videos dominated by pure-color frames.
            self.add_issue(item, "pure_video_frames")
        if under_count / total > max_bad_ratio:  # Flag videos dominated by under-exposed frames.
            self.add_issue(item, "video_under_exposure")
        if over_count / total > max_bad_ratio:  # Flag videos dominated by over-exposed frames.
            self.add_issue(item, "video_over_exposure")
        if high_noise_count / total > max_bad_ratio:  # Flag videos dominated by noisy frames.
            self.add_issue(item, "video_high_noise")
        return item

class FreezeFrameDetectOperator(VideoOperator):
    operator_name: str = "freeze_frame_detect"  # Operator identifier used by workflow configs and the registry.

    def process(self, item: dict) -> dict:
        """Detect freeze-frame behavior across sampled key frames.

        Business logic:
            1. Measure frame-to-frame grayscale differences.
            2. Estimate the ratio of near-identical consecutive frames.
            3. Add a freeze-frame issue when the ratio exceeds the configured threshold.

        Args:
                item (dict): Current sample dictionary.

        Returns:
            dict[str, Any]: Updated sample dictionary.

        Examples:
            >>> process
            process
        """
        frame_paths = item.get("intermediate", {}).get("keyframe_paths", [])
        if len(frame_paths) < 2:  # Return a neutral metric when there are not enough frames to compare.
            self.set_metric(item, "freeze_frame_ratio", None)
            return item
        diffs = []
        previous = None
        for frame_path in frame_paths:  # Aggregate frame-difference statistics frame by frame.
            with Image.open(frame_path) as image:
                gray = image.convert("L").resize((48, 48))
                pixels = list(gray.getdata())
            if previous is not None:  # Start comparing against the previous frame from the second frame onward.
                diffs.append(mean(abs(left - right) for left, right in zip(previous, pixels)))
            previous = pixels
        freeze_threshold = float(self.config.get("freeze_diff_threshold", 1.5))
        frozen = sum(1 for diff in diffs if diff <= freeze_threshold)
        ratio = frozen / max(len(diffs), 1)
        self.set_metric(item, "frame_diff_mean", round(mean(diffs), 4) if diffs else None)
        self.set_metric(item, "freeze_frame_ratio", round(ratio, 4))
        if ratio > float(self.config.get("max_freeze_frame_ratio", 0.75)):  # Flag freeze frames when near-identical frames dominate.
            self.add_issue(item, "freeze_frames")
        return item

class FrameQRCodeDetectOperator(VideoOperator):
    operator_name: str = "frame_qr_code_detect"  # Operator identifier used by workflow configs and the registry.

    def process(self, item: dict) -> dict:
        """Detect QR codes across sampled video frames.

        Business logic:
            1. Scan a bounded number of key frames for QR content.
            2. Record which frames contain QR-like content and any decoded text.
            3. Add a video-level QR-code issue when any frame is positive.

        Args:
                item (dict): Current sample dictionary.

        Returns:
            dict[str, Any]: Updated sample dictionary.

        Examples:
            >>> process
            process
        """
        frame_paths = item.get("intermediate", {}).get("keyframe_paths", [])
        if not frame_paths:  # Skip frame-level checks when no key frames are available.
            return item
        detected_frames = []
        for frame_path in frame_paths[: int(self.config.get("max_scan_frames", 8))]:  # Scan a bounded set of frames for QR detections.
            detected, text = self._detect_qr(Path(frame_path))
            if detected:  # Keep evidence only for frames with confirmed or likely QR content.
                detected_frames.append({"frame": str(frame_path), "text": text[:120]})
        self.set_metric(item, "video_qr_detected", bool(detected_frames))
        self.set_metric(item, "video_qr_detected_frames", detected_frames)
        if detected_frames:  # Flag the video when at least one frame contains a QR code.
            self.add_issue(item, "video_qrcode_detected")
        return item

    def _detect_qr(self, frame_path: Path) -> tuple[bool, str]:
        """Detect QR content inside a single frame.

        Business logic:
            1. Prefer OpenCV QR detection for ASCII-safe frame paths.
            2. Fall back to a local heuristic when OpenCV fails or is unavailable.
            3. Return the detection result and any decoded text.

        Args:
                frame_path (Path): Frame path.

        Returns:
            tuple[bool, str]: Detection result and decoded text.

        Examples:
            >>> _detect_qr
            _detect_qr
        """
        if cv2 is not None and str(frame_path).isascii():  # Prefer OpenCV QR detection when it is available and the frame path is ASCII-safe.
            try:
                image = cv2.imread(str(frame_path))
                if image is not None:  # Run pixel-level detection only after the frame loads successfully.
                    detector = cv2.QRCodeDetector()
                    decoded_text, points, _ = detector.detectAndDecode(image)
                    return bool(decoded_text) or points is not None, str(decoded_text or "")
            except Exception:
                return self._fallback_detect(frame_path), ""
        return self._fallback_detect(frame_path), ""

    def _fallback_detect(self, frame_path: Path) -> bool:
        """Detect QR-like patterns in a frame with a local heuristic.

        Business logic:
            1. Analyze a grayscale thumbnail of the frame.
            2. Measure dark-corner and transition patterns characteristic of QR codes.
            3. Return whether the frame looks QR-like.

        Args:
                frame_path (Path): Frame path.

        Returns:
            bool: Whether the frame looks QR-like.

        Examples:
            >>> _fallback_detect
            _fallback_detect
        """
        try:
            with Image.open(frame_path) as image:
                gray = image.convert("L").resize((192, 192))
                pixels = list(gray.getdata())
        except Exception:
            return False
        width = 192
        corner = 70
        corners = [
            (0, 0),
            (width - corner, 0),
            (0, width - corner),
            (width - corner, width - corner),
        ]
        for x0, y0 in corners:  # Scan each corner where QR locator patterns are most likely to appear.
            crop = []
            rows = []
            for y in range(y0, y0 + corner):  # Read each row of pixels inside the current corner crop.
                start = y * width + x0
                row = pixels[start : start + corner]
                rows.append(row)
                crop.extend(row)
            dark_ratio = sum(1 for pixel in crop if pixel < 80) / max(len(crop), 1)
            bright_ratio = sum(1 for pixel in crop if pixel > 220) / max(len(crop), 1)
            transitions = 0
            total_pairs = 0
            for row in rows:  # Count horizontal black-white transitions in each crop row.
                for left, right in zip(row, row[1:]):  # Adjacent brightness changes estimate QR-like texture density.
                    transitions += int((left < 128) != (right < 128))
                    total_pairs += 1
            for y in range(len(rows) - 1):  # Count vertical transitions between adjacent crop rows.
                for x in range(corner):  # Compare upper and lower pixel brightness in the current column.
                    transitions += int((rows[y][x] < 128) != (rows[y + 1][x] < 128))
                    total_pairs += 1
            transition_ratio = transitions / max(total_pairs, 1)
            if dark_ratio > 0.12 and bright_ratio > 0.25 and transition_ratio > 0.08:  # Treat the frame as QR-like when darkness, contrast, and transition density all exceed thresholds.
                return True
        return False

class VLMFrameDescribeOperator(VideoOperator):
    operator_name: str = "vlm_frame_describe"  # Operator identifier used by workflow configs and the registry.

    def setup(self) -> None:
        """Initialize external dependencies for VLM-based frame description.

        Business logic:
            1. Read client or model settings from operator config.
            2. Create a reusable vision client for frame-description calls.
            3. Keep setup side effects limited to client creation.

        Args:
                None: This hook does not take input parameters.

        Returns:
            None: The hook prepares runtime client state in place.

        Examples:
            >>> setup
            setup
        """
        self.client = OpenAICompatibleVisionClient(self.config.get("vlm", self.config))  # Reusable external client configured from operator settings.

    def process(self, item: dict) -> dict:
        """Describe sampled video frames with a VLM or local fallback.

        Business logic:
            1. Prefer provided visual keywords when available.
            2. Otherwise query the VLM over a bounded set of key frames.
            3. Record descriptions, keyword hints, unsafe frames, and fallback reasons.

        Args:
                item (dict): Current sample dictionary.

        Returns:
            dict[str, Any]: Updated sample dictionary.

        Examples:
            >>> process
            process
        """
        if self.should_skip(item):  # Skip work when an earlier operator already ruled out video processing.
            return item
        payload = item.get("payload", {})
        provided_keywords = as_list(payload.get("visual_keywords") or item.get("meta", {}).get("visual_keywords") or [])
        mode = "provided_fallback" if provided_keywords else "local_fallback"
        descriptions = []
        unsafe_frames = []
        api_keywords: list[str] = []
        if self.client.is_enabled():  # Use the API path when the external model is fully configured.
            errors = []
            for frame_path in item.get("intermediate", {}).get("keyframe_paths", [])[: int(self.config.get("max_vlm_frames", 4))]:  # Aggregate VLM frame descriptions over a bounded number of key frames.
                result, error = self._call_vlm(Path(frame_path))
                if error:  # Record fallback reasons when a frame-description call fails.
                    errors.append(error)
                    continue
                descriptions.append(str(result.get("description", "") or ""))
                api_keywords.extend(as_list(result.get("visual_keywords", [])))
                if bool(result.get("unsafe", False)) and bounded_float(result.get("confidence", 0.0)) >= float(
                    self.config.get("min_risk_confidence", 0.45)
                ):
                    unsafe_frames.append({"frame": str(frame_path), "reason": str(result.get("reason", ""))[:160]})
            if api_keywords or descriptions:  # Treat the API path as successful when it returns keywords or descriptions.
                mode = "api"
            elif errors:
                self.add_issue(item, "vlm_video_api_fallback")
                self.set_metric(item, "vlm_video_error", errors[0])

        local_risk = self._local_visual_risk(item)
        if local_risk:  # Append local visual-risk evidence when heuristic checks hit.
            unsafe_frames.extend(local_risk)
        visual_keywords = sorted({token.lower() for token in provided_keywords + api_keywords if str(token).strip()})
        item.setdefault("intermediate", {})["visual_keywords"] = visual_keywords
        if descriptions:  # Persist frame descriptions when available for later consistency checks.
            item["intermediate"]["vlm_frame_descriptions"] = descriptions
        self.set_metric(item, "vlm_frame_mode", mode)
        self.set_metric(item, "visual_keywords", visual_keywords)
        self.set_metric(item, "video_visual_safety_hits", unsafe_frames)
        if unsafe_frames:  # Flag the video when any frame is considered unsafe.
            self.add_issue(item, "video_safety_risk")
        return item

    def _call_vlm(self, frame_path: Path) -> tuple[dict[str, Any], str]:
        """Call the vision model to describe one frame.

        Business logic:
            1. Assemble a frame-description prompt.
            2. Send the request and read the JSON response.
            3. Return the structured result and any error message.

        Args:
                frame_path (Path): Frame path.

        Returns:
            tuple[dict[str, Any], str]: Structured result and error string.

        Examples:
            >>> _call_vlm
            _call_vlm
        """
        prompt = (
            "Describe this key frame for a video denoising pipeline. Return strict JSON only with keys: "
            "description(string), visual_keywords(list), unsafe(boolean), risk_category(string), confidence(0-1), reason(string)."
        )
        return self.client.chat_json(frame_path, prompt)

    def _local_visual_risk(self, item: dict) -> list[dict[str, str]]:
        """Detect simple frame-risk markers with local heuristics.

        Business logic:
            1. Scan a bounded set of key frames.
            2. Measure warning-red ratios in resized RGB thumbnails.
            3. Return frame-level risk hits detected by the local heuristic.

        Args:
                item (dict): Current sample dictionary.

        Returns:
            list[dict[str, str]]: Local frame-risk hits.

        Examples:
            >>> _local_visual_risk
            _local_visual_risk
        """
        hits = []
        for frame_path in item.get("intermediate", {}).get("keyframe_paths", [])[: int(self.config.get("max_local_frames", 8))]:  # Aggregate local risk signals frame by frame.
            try:
                with Image.open(frame_path) as image:
                    rgb = image.convert("RGB").resize((160, 160))
                    pixels = list(rgb.getdata())
            except Exception:
                continue
            red_ratio = sum(1 for r, g, b in pixels if r > 170 and g < 85 and b < 85) / max(len(pixels), 1)
            if red_ratio > float(self.config.get("max_warning_red_ratio", 0.12)):  # Flag frames whose warning-red ratio exceeds the configured threshold.
                hits.append({"frame": str(frame_path), "reason": "local_warning_red_marker"})
        return hits
