# Gemini Codebase Analysis

This document provides a detailed analysis of the codebase, including a file tree and a breakdown of each file's purpose and functions.

## File Tree

```
./
├───.gitignore
├───AGENTS.md
├───app_nice_version.py
├───app_ocr.py
├───app_workflow.py
├───app.py
├───autogui.py
├───CLAUDE.md
├───CODEMAP.md
├───codex.png
├───drawing.js
├───index.html
├───notDone.md
├───README.md
├───requirements.txt
├───ROADMAP.md
├───run_gemini.py
├───run_post.py
├───run_workflow.py
├───solar.py
├───startYolo.md
├───STRATEGY_IMPLEMENTATION_STATUS.md
├───SUMMARY.md
├───test.py
├───TODO.md
├───yolo_nice_version_endpoint.md
├───yolo_ocr_endpoint.md
├───yolo_omni_style.py
├───yolo_ui copy.py
├───yolo_ui.py
├───yolo.py
├───__pycache__/
├───.claude/
│   └───settings.local.json
├───.git/...
├───config/
│   └───classes.json
├───core/
│   ├───anchors.py
│   ├───candidates.py
│   ├───capture.py
│   ├───costs.py
│   ├───detectors.py
│   ├───executor.py
│   ├───gemini_client.py
│   ├───landmarks.py
│   ├───llm_client.py
│   ├───llm_router.py
│   ├───locator.py
│   ├───mapping.py
│   ├───memory_strategy.py
│   ├───memory.py
│   ├───ocr_client.py
│   ├───ops_new.py
│   ├───ops.py
│   ├───prompt_builder.py
│   ├───report_events.py
│   ├───reporter.py
│   ├───sm.py
│   ├───strategy_adapter.py
│   ├───strategy_exec.py
│   ├───strategy_schema.py
│   ├───strategy_selector.py
│   ├───strategy_store.py
│   ├───timeline.py
│   ├───types.py
│   ├───workflow.py
│   ├───yolo_client.py
│   └───__pycache__/
├───ddl/
├───docs/
├───flows/
│   ├───auto_workflow.json
│   ├───xhs_longform_vision.json
│   ├───xhs_search_reply_fixed.json
│   └───xhs_search_reply.json
├───getcontent/
├───myenv/
│   ├───bin/...
│   ├───include/...
│   ├───lib/...
│   └───share/...
├───out/
├───scripts/
├───tools/
│   ├───build_timeline.py
│   ├───enable_strategy_env.sh
│   ├───replay_run.py
│   ├───report_gen.py
│   ├───run_with_timeline.sh
│   ├───run_workflow_gen.py
│   └───smoke_suite.py
└───weights/...
```

## File-by-File Analysis

### /.gitignore

*   **Description:** This file specifies intentionally untracked files that Git should ignore. It includes rules for byte-compiled files, distribution directories, virtual environments, test reports, and OS-generated files.

### /app.py

*   **Description:** This file sets up a FastAPI server for YOLO object detection. It provides an endpoint `/predict` that takes an image and returns a list of detections. It includes extensive helper functions for drawing bounding boxes and labels directly on the image in a visually appealing and adaptive way.
*   **Functions:**
    *   `_np_to_base64_png(img_np)`: Converts a NumPy array (OpenCV image) to a base64 encoded PNG data URL.
    *   `_read_image_bytes(...)`: Reads image data from an uploaded file, a base64 string, or a URL.
    *   `_pil_to_bgr(pil_im)`: Converts a PIL image to a BGR NumPy array for OpenCV.
    *   `_sort_indices_tl(xyxy)`: Sorts bounding box indices from top-to-bottom, then left-to-right.
    *   `_font_scale_from_px(...)`: Calculates the OpenCV `fontScale` required to achieve a desired font height in pixels.
    *   `_clip_int(v, lo, hi)`: Clamps an integer value within a given range.
    *   `_draw_inside_label(...)`: Intelligently draws a label inside a bounding box, trying corners first, then a top band, and adapting font size as needed.
    *   `_draw_scene_inside(...)`: Orchestrates the drawing of all boxes and labels on an image. It dynamically calculates font sizes based on image and box dimensions.
    *   `health()`: A health check endpoint that returns the status and model information.
    *   `predict(...)`: The main prediction endpoint. It receives an image, runs YOLO inference, processes the results to assign stable IDs, and optionally draws the annotated image before returning the detections.

### /app_nice_version.py

*   **Description:** This appears to be a duplicate or a slightly modified version of `app.py`. Its functionality is identical, providing a FastAPI endpoint for YOLO object detection with advanced drawing capabilities.

### /app_ocr.py

*   **Description:** This file extends the YOLO FastAPI server with OCR capabilities. It uses PaddleOCR (preferred) or EasyOCR (fallback) to perform OCR on the detected bounding boxes. The `/predict` endpoint can perform detection and then run OCR on either the full image, individual cropped boxes, or a fused combination of both.
*   **Classes:**
    *   `OCRBackend`: A wrapper class that unifies the interfaces for PaddleOCR and EasyOCR. It handles initialization and provides a single `read` method.
*   **Functions:**
    *   Includes most of the same helper functions as `app.py` for image handling and drawing.
    *   `_poly_center(poly)`: Calculates the center of a polygon.
    *   `_rect_intersects_poly(...)`: Checks if a rectangle intersects with a polygon, used for fusing global OCR results with detected boxes.
    *   `_expand_box(...)`: Expands a bounding box by a given ratio.
    *   `_dedup_lines(lines)`: Deduplicates OCR lines based on text content and geometry.
    *   `health()`: Health check endpoint, also reports availability of OCR backends.
    *   `predict(...)`: The main endpoint. It performs YOLO detection, then, based on the `box_ocr_mode`, runs OCR on the full image and/or individual crops. It fuses the results to associate OCR text with each detection.

### /app_workflow.py

*   **Description:** This file defines a FastAPI router for generating automation workflows. It exposes an endpoint that takes a task description and uses an LLM to generate a JSON-based workflow definition.
*   **Functions:**
    *   `_slug(s)`: Converts a string into a URL-friendly slug.
    *   `generate_workflow(req)`: The main endpoint. It takes a `WorkflowGenReq`, builds a prompt using `build_workflow_prompt`, calls an LLM to get a JSON response, and optionally saves the resulting workflow to a file in the `flows/` directory.

### /autogui.py

*   **Description:** A script that uses `pyautogui` to automate simple UI interactions. It continuously watches the screen for two images (`codex.png` and `codexstop.png`) and performs actions (pressing Enter, typing text) when they are found.
*   **Functions:**
    *   `bring_terminal_to_front()`: Activates the Terminal or iTerm application on macOS.
    *   `locate(image_path)`: Finds the center coordinates of a given image on the screen.
    *   `press_enter()`: Simulates pressing the Enter key.
    *   `type_and_enter(text)`: Types the given text and then presses Enter.
    *   `main()`: The main loop that orchestrates the screen watching and actions.

### /config/classes.json

*   **Description:** A JSON configuration file that seems to hold parameters for UI interaction, such as click padding, minimum confidence for detection, retry counts, and timeouts.

### /core/anchors.py

*   **Description:** This module provides functions for creating and matching visual anchors for UI elements. It supports template matching, ORB features, and text-based anchors. It also includes a `RoutesStore` for persisting and retrieving successful navigation routes to avoid re-learning common paths.
*   **Classes:**
    *   `RoutesStore`: Manages a persistent log (`routes.jsonl`) of navigation actions (signatures, goals, clicks). It can look up successful past routes to speed up automation and track success rates.
*   **Functions:**
    *   `anchors_from(bgr, bbox, ...)`: Generates a template-based anchor from a bounding box on an image.
    *   `anchors_match(bgr, anchors)`: Matches a legacy template anchor against a new image.
    *   `adjust_*_anchor(...)`: A family of functions to dynamically adjust anchor thresholds (template, ORB) based on success or failure, enabling self-healing.
    *   `gen_templates(...)`, `gen_orb_features(...)`: Generate different types of anchors for a given bounding box.
    *   `match_template(...)`, `match_orb(...)`: Perform matching for different anchor types.
    *   `auto_select_anchors(bgr, bbox)`: Heuristically selects the best combination of anchors (row, action, text) for a given UI element.
    *   `state_anchors_from(...)`, `state_anchors_vote(...)`: Functions to create and verify a signature for an entire page state, combining templates, OCR, and URL hints.

### /core/candidates.py

*   **Description:** This module contains functions for processing and filtering detected UI elements (candidates) based on their geometry and relationship to other elements.
*   **Functions:**
    *   `iou(a, b)`: Calculates the Intersection over Union (IoU) of two bounding boxes.
    *   `box_to_geom(bbox, ...)`: Converts a bounding box to a dictionary of normalized geometric features (center, width, height, area, aspect ratio).
    *   `region_tag(cx, cy)`: Assigns a coarse region tag (e.g., 'topbar', 'content') based on normalized coordinates.
    *   `is_overlap_modal(...)`: Checks if a bounding box overlaps with a known modal dialog.
    *   `yolo_to_geom_candidates(...)`: Converts a raw YOLO JSON response into a structured list of candidates with geometric features, ready for a picker model.

### /core/capture.py

*   **Description:** A simple screen capture utility. It wraps `pyautogui` and handles device pixel ratio (DPR) to ensure coordinate systems are consistent.
*   **Classes:**
    *   `GrabResult`: A dataclass to hold the screenshot image, DPR, and pixel dimensions.
    *   `ScreenCapture`: The main class that provides the `screenshot()` method and helper functions to convert between image formats.

### /core/costs.py

*   **Description:** This module implements a cost and budget management system for the agent. It defines budgets for LLM calls and performance, tracks usage, and provides policies for degrading service (e.g., skipping calls, using smaller models) when budgets are exceeded.
*   **Classes:**
    *   `Budget`: Dataclass to define the maximum number of calls, tokens, and time limits.
    *   `Usage`: Dataclass to track the current usage against the budget.
    *   `CostGuard`: The main class that enforces the budget, tracks usage, and determines if a degradation policy should be applied.
    *   `ImageDegradationPolicy`: Defines specific policies for how to degrade image quality to save tokens for different types of LLM calls (picker, arbiter).

### /core/detectors.py

*   **Description:** This module provides functions for detecting specific UI patterns like loading spinners, toasts, and modal dialogs using template matching and heuristics.
*   **Functions:**
    *   `_load_templates(...)`: Loads and caches template images from a directory.
    *   `_multi_scale_match(...)`: Performs template matching across multiple scales.
    *   `detect_loading(bgr)`, `detect_toast(bgr)`, `detect_close(bgr)`: Functions that use template matching to detect specific UI components.
    *   `detect_modal(bgr)`: A heuristic-based detector for modal dialogs, looking at overlay darkness and edge density.

### /core/executor.py

*   **Description:** This module is responsible for executing low-level UI actions like moving the mouse, clicking, typing, and scrolling. It wraps `pyautogui` and adds features like human-like jitter and robust text input methods.
*   **Classes:**
    *   `Executor`: The main class providing methods for UI control.
*   **Functions:**
    *   `move_to(x, y, ...)`: Moves the mouse to a specified coordinate with jitter and easing.
    *   `click(x, y, ...)`: Moves and clicks at a coordinate, handling DPR scaling.
    *   `type_text(text, ...)`: Types text, with an 'auto' mode that can switch to clipboard pasting for better Unicode support. It includes platform-specific implementations for macOS and Windows for more reliable Unicode typing.
    *   `scroll(clicks)`: Scrolls the mouse wheel.
    *   `go_back()`: Simulates a browser 'back' action.

### /core/gemini_client.py

*   **Description:** A client for interacting with the Google Gemini API. It handles API key management, constructing the request payload (including images), and parsing the response.
*   **Functions:**
    *   `load_env_from_dotenv(...)`: Loads environment variables from a `.env` file.
    *   `read_image_b64(path)`: Reads an image file and encodes it as a base64 string.
    *   `call_gemini(...)`: Constructs the request and calls the Gemini API.
    *   `extract_text(response_json)`: Extracts the text content from a Gemini API response.
    *   `parse_first_json(text)`: A robust JSON parser that finds and parses the first valid JSON object within a string, even if it's embedded in other text or markdown.
    *   `generate_json(...)`: A wrapper that calls the Gemini API and ensures a valid JSON object is returned, raising an error if parsing fails.

### /core/landmarks.py

*   **Description:** This module focuses on identifying high-level, persistent UI landmarks on a page, such as a search bar, sidebar, or tab bar. It uses a combination of YOLO detections, OCR hints, and positional rules to robustly identify these regions.
*   **Functions:**
    *   `_score_candidate(...)`: Scores a candidate UI element for a specific landmark role based on its class, text, and position.
    *   `detect_landmarks(...)`: The main function that takes all detected items and identifies the most likely candidate for each landmark role.
    *   `detect_landmarks_cached(...)`: A cached version of `detect_landmarks` to avoid re-computation on the same screen state.

### /core/llm_client.py

*   **Description:** This file provides a unified interface for calling various LLM providers (Gemini, OpenAI, DeepSeek, NVIDIA). It abstracts the differences in their API request/response formats, allowing the rest of the application to use a single `call_llm` function.
*   **Functions:**
    *   `_to_openai_messages_from_gemini(...)`: Converts the Gemini-style message format (used internally) to the OpenAI-compatible format.
    *   `call_llm(...)`: The main entry point. It takes a provider name and routes the call to the appropriate backend, handling API keys and request formatting. It also supports a fallback mechanism.
    *   `extract_text_generic(response_json)`: Extracts text content from a response, supporting both Gemini and OpenAI-compatible formats.
    *   `generate_json(...)`: A wrapper that calls the selected provider and parses a JSON object from the response.

### /core/llm_router.py

*   **Description:** This module acts as a gateway for all LLM calls, integrating the `CostGuard` to enforce budget and degradation policies. It decides whether to allow, skip, or degrade a call based on current usage.
*   **Classes:**
    *   `LLMRouter`: The main class that orchestrates the calls.
*   **Functions:**
    *   `_apply_image_degradation(...)`: Applies the image degradation policies (e.g., downscaling) before sending an image to the LLM.
    *   `maybe_call(...)`: The primary method. It checks the budget with `CostGuard`, applies degradations, makes the actual LLM call via `llm_client`, and records the usage and results.

### /core/locator.py

*   **Description:** This module contains logic for selecting the best UI element (detection) from a list of candidates based on a target class and scoring heuristics.
*   **Functions:**
    *   `_center_bias(...)`: A scoring function that gives higher weight to elements closer to the center of the screen.
    *   `select_best(...)`: Filters detections by class and confidence, then scores them based on confidence, area, and center bias to choose the best one.
    *   `bbox_center(...)`: Calculates the center point of a bounding box.

### /core/mapping.py

*   **Description:** This module is responsible for coordinate mapping. It translates bounding boxes from the model's inference space (which might be normalized or letterboxed) to the physical screen coordinates required for clicks.
*   **Functions:**
    *   `to_capture_coords(...)`: Converts a bounding box from the pre-processed frame coordinates back to the original capture coordinates, undoing letterboxing and scaling.
    *   `click_point_from_box(...)`: Calculates the optimal click point within a bounding box, with special logic for text fields.
    *   `map_id_to_screen_point(...)`: The main function that combines the other two to map a detected bounding box to a final screen (x, y) coordinate for the executor.

### /core/memory.py

*   **Description:** This module provides a simple, persistent memory store for the agent. It logs the outcomes of actions on a per-page basis, allowing it to maintain a blacklist of failed clicks and provide a short-term history to the LLM to avoid repeating mistakes.
*   **Classes:**
    *   `MemoryStore`: Manages a JSONL file (`memory.jsonl`) to store action outcomes. It provides methods to record results, retrieve a blacklist of failed IDs, and summarize recent history.

### /core/memory_strategy.py

*   **Description:** This module implements a more advanced memory system specifically for automation strategies. It tracks the success rate of different strategies using an Exponential Moving Average (EMA) for health, allowing the system to learn which strategies are reliable for particular page types.
*   **Classes:**
    *   `StrategyMemory`: A dataclass for a single strategy memory entry, tracking its success/failure counts and EMA health.
    *   `StrategyMemoryStore`: Manages the persistence and retrieval of `StrategyMemory` objects, providing methods to record outcomes and get a list of healthy strategies.

### /core/ops.py & /core/ops_new.py

*   **Description:** These modules define a library of "structural operators" used by automation strategies. These are functions that operate on lists of UI items, allowing for relational queries like "find the item below this landmark" or "get the third item in this container." `ops.py` appears to be an older, bbox-based version, while `ops_new.py` is an enhanced, `Item`-based version.
*   **Functions (ops_new.py):**
    *   `within(items, container)`: Filters items that are inside a container.
    *   `below(items, landmark)`: Filters items that are below a landmark.
    *   `right_of(items, landmark)`: Filters items to the right of a landmark.
    *   `nearest_to(items, landmark)`: Finds the item closest to a landmark.
    *   `sort_by_y(items)`: Sorts items by their Y-coordinate.
    *   `cluster_list(items)`: Groups items into rows based on Y-proximity.
    *   `gridize(items)`: Organizes items into a 2D grid.
    *   `has_attr(items, attr)`: Filters items that have a specific attribute (e.g., 'unread').
    *   `text_match(items, text)`: Filters items by their OCR text.

### /core/prompt_builder.py

*   **Description:** This module is responsible for constructing the complex prompts sent to the LLMs for various tasks (picker, planner, verifier). It defines several system prompts and functions to assemble the final payload.
*   **Constants:**
    *   `SYSTEM_TEMPLATE_UI_OUTLINE`, `PICKER_VISION_SYSTEM`, `POP_VISION_SYSTEM`, etc.: These are the large, detailed system prompts that instruct the LLM on its task, rules, and output schema.
*   **Functions:**
    *   `build_user_payload(...)`: Constructs the main JSON payload for the vision picker, including goal, context, and candidate information.
    *   `build_messages(...)`: Combines a system prompt and a user payload into the final message list for the LLM.
    *   `build_workflow_prompt(...)`: Builds the meta-prompt used to ask an LLM to generate an entire automation workflow from a natural language task description.

### /core/report_events.py

*   **Description:** This module defines a schema for structured event logging and provides functions to emit these events to a JSONL file (`report_events.jsonl`). This creates a detailed, machine-readable log of a workflow run, which is used by `report_gen.py` to create HTML reports.
*   **Functions:**
    *   `emit_*`: A family of functions (`emit_run_begin`, `emit_step_end`, `emit_llm_call`, etc.) for logging specific, structured events during a workflow run.
    *   `read_events(...)`, `filter_events_by_*`, `get_step_summary(...)`: Utilities for reading and parsing the generated event log.

### /core/reporter.py

*   **Description:** This module is responsible for generating human-readable HTML reports from a workflow run. It logs steps, saves screenshots, and then compiles everything into a single HTML file.
*   **Classes:**
    *   `StepLog`: A dataclass to hold information about a single step in the workflow.
    *   `Reporter`: The main class that collects `StepLog` objects and contains the logic to render the final HTML report, including metrics and before/after/overlay images for each step.

### /core/sm.py (StateMachine)

*   **Description:** A very simple state machine helper. Its primary purpose is to poll the screen until a specific UI element (identified by its class name) appears.
*   **Classes:**
    *   `StateMachine`: Provides a `wait_for_any` method that repeatedly takes screenshots and runs detection until one of the target classes is found or a timeout is reached.

### /core/strategy_adapter.py

*   **Description:** This module acts as an adapter between the raw YOLO/OCR outputs and the more abstract, `Item`-based strategy execution system. It converts detections to `Item` objects, adds attributes, and infers page context.
*   **Functions:**
    *   `yolo_detection_to_item(...)`: Converts a raw detection object into a structured `Item`.
    *   `preprocess_items_with_attrs(...)`: Adds attributes like 'unread' to items based on OCR and color analysis.
    *   `create_strategy_context(...)`: The main function that orchestrates the conversion of raw inputs (detections, OCR lines) into the full context needed by the strategy selection and execution modules.

### /core/strategy_exec.py

*   **Description:** This is the execution engine for the abstract strategies selected by the `StrategySelector`. It contains the implementation logic for each `strategy_id`.
*   **Functions:**
    *   `exec_strategy(spec, all_items, ...)`: The core function that takes a `StrategySpec` and executes the corresponding logic (e.g., `LIST_TOPMOST_WITH_ATTR`, `GRID_BY_ROWCOL`) on the list of UI `Item`s.
    *   `exec_strategy_with_fallback(...)`: A wrapper that executes the primary strategy and, if it fails, tries the specified fallback strategy.

### /core/strategy_schema.py

*   **Description:** This module is responsible for validating and sanitizing the JSON output from the strategy-selection LLM. It ensures that the generated strategies are well-formed and use only allowed IDs and parameters, preventing malformed or "hallucinated" strategies from being executed.
*   **Constants:**
    *   `ALLOWED_STRATEGY_IDS`, `STRATEGY_PARAM_WHITELIST`: Whitelists for validating the LLM's output.
*   **Functions:**
    *   `sanitize_strategy_json(...)`: The main validation function that cleans and validates the raw JSON string from the LLM.

### /core/strategy_selector.py

*   **Description:** This module is responsible for deciding which high-level automation strategy to use for a given page and goal. It can use memory of past successful strategies or query an LLM to generate a new one. It incorporates the M2 trigger logic to decide *when* to invoke the strategy layer.
*   **Classes:**
    *   `StrategySelector`: The main class that manages strategy selection.
*   **Functions:**
    *   `should_trigger_strategy_llm(...)`: Implements the M2 logic to decide if the situation warrants calling the LLM for a new strategy (e.g., after repeated picker failures).
    *   `select_from_memory(...)`: Retrieves a known-good strategy from the `StrategyMemoryStore`.
    *   `decide(...)`: The main entry point. It checks the trigger conditions, tries to select a strategy from memory, and if necessary, calls the LLM to generate a new strategy specification.

### /core/strategy_store.py

*   **Description:** A persistent store for logging the outcome of strategy executions. It's similar to `RoutesStore` but is keyed by strategy specifications. It tracks the EMA success rate of each strategy to learn which ones are reliable.
*   **Classes:**
    *   `StrategyStore`: Manages the `strategies.jsonl` log file, providing methods to record strategy outcomes and look up previously successful strategies.

### /core/timeline.py

*   **Description:** A simple utility for creating a chronological, human-readable log file (`timeline.log`) for a run. It allows different parts of the system to emit timestamped events to a central log, making it easier to debug the sequence of operations.
*   **Functions:**
    *   `init(...)`: Initializes the timeline for a new run.
    *   `event(src, msg, ...)`: Appends a new event to the timeline log file.

### /core/types.py

*   **Description:** This file defines the core data structures (`dataclasses`) used throughout the automation framework, such as `Item`, `Landmark`, and `StrategySpec`. This ensures a consistent data model across different modules.

### /core/workflow.py

*   **Description:** This is the main workflow execution engine. It reads a JSON-defined workflow and orchestrates the execution of actions (e.g., `screenshot`, `detect`, `click`, `autostep`). The `autostep` action is a key component, encapsulating the entire perceive-decide-act loop for a single step, including the logic for replaying routes, falling back to the LLM picker, and invoking the strategy layer.
*   **Classes:**
    *   `WFConfig`: A dataclass for workflow configuration.
    *   `WorkflowRunner`: The main class that runs the workflow.
*   **Functions:**
    *   `_signature(...)`, `_sig_sim(...)`: Functions to generate and compare page signatures to detect state changes.
    *   `act_*`: A family of functions that implement the primitive actions defined in the workflow JSON (e.g., `act_screenshot`, `act_click`).
    *   `_autostep(cfg)`: The implementation of the complex `autostep` action. This is the heart of the agent's decision-making, combining route replay, strategy selection, and the vision-picker LLM call with budget control.
    *   `run(start_state)`: The main entry point to start the execution of the workflow from a given state.

### /core/yolo_client.py

*   **Description:** A client for the local YOLO FastAPI server. It provides a simple interface to send an image for inference and parse the resulting detections.
*   **Classes:**
    *   `Detection`: A dataclass for a single YOLO detection.
    *   `YoloClient`: The main class with an `infer` method to call the API and a `to_detections` method to parse the response.

### /drawing.js

*   **Description:** A simple JavaScript file for a web-based drawing application. It handles mouse events on an HTML canvas to allow the user to draw lines. It is used by `index.html`.

### /flows/

*   **Description:** This directory contains JSON files that define automation workflows.
    *   `auto_workflow.json`: A dynamically generated workflow.
    *   `xhs_longform_vision.json`, `xhs_search_reply.json`, `xhs_search_reply_fixed.json`: Pre-defined workflows for automating tasks on the Xiaohongshu (XHS) website.

### /index.html

*   **Description:** A simple HTML page that sets up a canvas and includes `drawing.js` to create a basic drawing application.

### /requirements.txt

*   **Description:** A standard Python requirements file listing the project's dependencies, such as `fastapi`, `ultralytics`, `torch`, and `opencv`.

### /run_gemini.py

*   **Description:** A command-line script to directly invoke the Gemini LLM with a structured prompt for UI element selection. It takes an image, a YOLO JSON file, and a goal, then builds and sends the request, saving the result.

### /run_post.py

*   **Description:** A simple runner script that demonstrates a single automation step: it takes a screenshot, detects a specific UI element (`post_plus_button`), and clicks it. It's a minimal example of the core agent loop.

### /run_workflow.py

*   **Description:** A command-line script to execute a workflow defined in a JSON file. It initializes the `WorkflowRunner` and starts the execution from the specified start state.

### /solar.py

*   **Description:** A Pygame script that creates a simple animation of a solar system with planets orbiting a central sun. This file seems unrelated to the main UI automation project.

### /test.py

*   **Description:** A simple Python script that uses OpenCV and Matplotlib to load an image, find contours, and display them. It appears to be for isolated testing or experimentation.

### /tools/

*   **Description:** This directory contains various utility and helper scripts for building, running, and analyzing workflows.
    *   `build_timeline.py`: Aggregates logs from a run to create a single, chronological timeline file.
    *   `enable_strategy_env.sh`: A shell script to set environment variables needed to enable the strategy layer and OCR.
    *   `replay_run.py`: A script to analyze `routes.jsonl` and provide metrics on replay success and anchor tuning.
    *   `report_gen.py`: Generates a comprehensive HTML report from the structured `report_events.jsonl` log file, including KPIs and per-step analysis.
    *   `run_with_timeline.sh`: A wrapper script that runs a workflow command while continuously refreshing the timeline log in the background.
    *   `run_workflow_gen.py`: A script to invoke the LLM to generate a new workflow JSON from a task description.
    *   `smoke_suite.py`: A script for running a workflow multiple times to gather stability and performance metrics, checking them against defined "Definition of Done" (DoD) gates.

### /yolo_*.py

*   **Description:** These files are related to running YOLO inference and visualizing the results.
    *   `yolo.py`: A script that uses the `roboflow` inference library to perform detection.
    *   `yolo_omni_style.py`: A script that runs YOLO detection and draws the results in a specific visual style (thin fonts, semi-transparent labels), mimicking the "OmniParser v2" style.
    *   `yolo_ui.py`, `yolo_ui copy.py`: Scripts that use the `ultralytics` library to run prediction and save the annotated image, with custom logic for font size and selection.
