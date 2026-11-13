"""Scene-analysis nodes for the Eclipse sequential loop."""
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

import folder_paths
from comfy_api.latest import io

from ..core import CATEGORY
from ..core.cache_artifacts import artifact_fingerprint, record_artifacts
from ..core.scene_analysis import (
    ANALYSIS_TYPE,
    APPEARANCE_MODES,
    FRAME_SOURCE_TYPE,
    H3_PERFORMANCE_PROMPT,
    JOBS_TYPE,
    PLAN_TYPE,
    STATE_TYPE,
    build_scene_analysis,
    collect_scene_description,
    detect_scenes,
    get_scene_job,
    h3_scene_part_inputs,
    limit_scene_cuts,
    load_scene_analysis,
    prepare_scene_jobs,
    save_scene_analysis,
    scene_analysis_review_report,
)
from ..core.video_run import STORAGE_TYPE

_CATEGORY = CATEGORY.MAIN.value + CATEGORY.VIDEO.value


class RvVideo_SceneDetector(io.ComfyNode):
    @classmethod
    def define_schema(cls):
        return io.Schema(node_id="Scene Detector [Eclipse Nova]", display_name="Scene Detector", category=_CATEGORY,
                         description="Detect hard cuts and persistent appearance changes across short blends. Scan every source frame on CPU and preserve source timing for separate scene descriptions; LM sampling and sizing are separate.",
                         inputs=[io.Video.Input("video", tooltip="Reference video to inspect. Cuts are timed from the start of this VIDEO, including its trim. Use matching audio and trim when transferring these timings to generation. A file-backed VIDEO keeps decoding memory bounded."),
                                 io.Int.Input("longest_side", default=128, min=16, max=4096,
                                              tooltip="Longest edge in pixels for CPU scene detection. Start with 128; increase it if subtle visual changes are missed. This is separate from Smart LM's Longest side setting for faces and gestures."),
                                 io.Float.Input("threshold", default=2.5, min=0.1, max=100, step=0.1,
                                                tooltip="Adaptive cut sensitivity. Lower values accept weaker changes and usually find more cuts; higher values require stronger changes. Start with 2.5. Use Scene Cut Limit to limit cut frequency after detection."),
                                 io.Int.Input("window_width", default=4, min=1, max=30,
                                              tooltip="Number of neighbouring source frames on each side used to estimate the local change baseline. This affects cut detection; Scene Analysis Plan controls how many frames reach the LM."),
                                 io.Float.Input("min_content", default=15, min=0, max=255,
                                                tooltip="Minimum absolute visual change for adaptive hard cuts, in addition to the adaptive threshold. Raise it to suppress tiny changes; values that are too high can miss cuts between similar shots. Gradual transitions use the separate gradual controls."),
                                 io.Int.Input("min_scene_frames", default=1, min=1, max=10000,
                                              tooltip="Minimum spacing between detected scenes, measured in original video frames. At 30 FPS, 30 frames is about one second. For a limit in seconds independent of source FPS, use Scene Cut Limit."),
                                 io.Float.Input("gradual_threshold", default=2.3, min=0.1, max=100, step=0.1, optional=True,
                                                tooltip="How strongly appearance must change compared with surrounding motion. Lower values accept weaker blends but can add false cuts."),
                                 io.Float.Input("gradual_min_change", default=0.2, min=0.01, max=1, step=0.01, optional=True,
                                                tooltip="Minimum persistent colour-distribution change for a blended transition. Lower values find subtler changes. Motion and lighting can still cause false detections; review the resulting scenes.")],
                         outputs=[io.Custom(PLAN_TYPE).Output("scene_plan", tooltip="Measured scene boundaries and the reference source. Connect to Scene Cut Limit, or directly to Scene Analysis Plan when no cut-rate limit is needed."),
                                  io.Int.Output("scene_count", tooltip="Number of detected scenes. The number of cuts is one less. Use Scene Analysis Plan's window_count to drive the description loop, since one scene can need several windows."),
                                  io.String.Output("report", tooltip="Detection summary with scene, cut and source-frame counts. Connect to Show Any to review it.")])

    @classmethod
    def execute(cls, video, longest_side=128, threshold=2.5, window_width=4, min_content=15,
                min_scene_frames=1, gradual_threshold=2.3, gradual_min_change=0.2):
        plan = detect_scenes(video, longest_side, threshold, window_width, min_content, min_scene_frames,
                             detect_gradual=True, gradual_threshold=gradual_threshold,
                             gradual_min_change=gradual_min_change)
        added = len(plan.metadata['detector']['gradual_cut_frames'])
        return io.NodeOutput(plan, len(plan.scenes),
                             f"{len(plan.scenes)} scenes / {len(plan.scenes) - 1} cuts; "
                             f"{added} blended transitions; {plan.metadata['frame_count']} source frames.")


class RvVideo_SceneCutLimit(io.ComfyNode):
    @classmethod
    def define_schema(cls):
        return io.Schema(node_id="Scene Cut Limit [Eclipse Nova]", display_name="Scene Cut Limit", category=_CATEGORY,
                         description="Filter an existing scene plan before frame sampling. Keep the earliest cut meeting the spacing limit and merge across excluded cuts. Original cut positions and the complete source duration stay intact; detection is not rerun when this limit changes.",
                         inputs=[io.Custom(PLAN_TYPE).Input("scene_plan", tooltip="Connect Scene Detector's scene_plan. This node filters the existing boundaries without decoding the video again."),
                                 io.Float.Input("max_cuts_per_second", default=0.0, min=0.0, max=60.0, step=0.1,
                                                tooltip="0: unlimited. 1: at least 1 second between cuts. 2: at least 0.5 seconds. 0.5: at least 2 seconds. Keeps the earliest eligible cut and merges across excluded cuts. Spacing also applies from the start; the final scene can be shorter. Changing this limit requires new sampling and descriptions for the merged scenes.")],
                         outputs=[io.Custom(PLAN_TYPE).Output("scene_plan", tooltip="Filtered scene plan for Scene Analysis Plan. Retained cuts keep their original positions, and the complete video duration is preserved."),
                                  io.Int.Output("scene_count", tooltip="Number of scenes after filtering. Sampling can split each scene into several analysis windows, so drive the loop with window_count instead."),
                                  io.String.Output("report", tooltip="Retained scene/cut counts, number of excluded cuts and effective minimum spacing. Connect to Show Any to compare settings.")])

    @classmethod
    def execute(cls, scene_plan, max_cuts_per_second=0.0):
        plan = limit_scene_cuts(scene_plan, max_cuts_per_second)
        excluded = len(scene_plan.scenes) - len(plan.scenes)
        spacing = f"minimum spacing {1 / max_cuts_per_second:g}s" if max_cuts_per_second else "unlimited"
        return io.NodeOutput(plan, len(plan.scenes),
                             f"{len(plan.scenes) - 1} cuts / {len(plan.scenes)} scenes; {excluded} cuts excluded; {spacing}. Retained cut positions are unchanged.")


class RvVideo_SceneAnalysisPlan(io.ComfyNode):
    @classmethod
    def define_schema(cls):
        return io.Schema(node_id="Scene Analysis Plan [Eclipse Nova]", display_name="Scene Analysis Plan", category=_CATEGORY,
                         description="Cache selected source frames on disk or in CPU RAM in one streaming pass. Every scene keeps its first and last frame. Long selections become overlapping windows, never additional cuts.",
                         inputs=[io.Custom(PLAN_TYPE).Input("scene_plan", tooltip="Connect Scene Detector, or Scene Cut Limit when limiting cut frequency. Sampling uses the scene ranges in this plan."),
                                 io.Combo.Input("sampling", options=["uniform", "every_nth"], default="uniform",
                                                tooltip="uniform spreads up to samples_per_scene images across each scene. every_nth takes every Nth original frame and ignores samples_per_scene. Both keep the scene's first and last frame."),
                                 io.Int.Input("samples_per_scene", default=8, min=2, max=10000,
                                              tooltip="Total image budget per scene in uniform mode; ignored in every_nth mode. To send up to 16 images together, set BOTH this value and max_frames to 16. Short scenes can provide fewer images. More samples capture finer movement but can add LM work."),
                                 io.Int.Input("every_nth", default=2, min=1, max=10000,
                                              tooltip="Used only in every_nth sampling mode. 1 selects every original frame; 2 selects every second frame. Selection restarts at each scene and keeps both endpoints. Smart LM's Every Nth is a second filter over these selected images; keep it at 1 to avoid sampling twice."),
                                 io.Int.Input("max_frames", default=8, min=2, max=256,
                                              tooltip="Maximum selected images in one LM request window. It does not increase samples_per_scene. For up to 16 images per request in uniform mode, set BOTH controls to 16 and use Smart LM Together with Every Nth = 1. Larger windows use more LM memory; longer selections split into overlapping windows."),
                                 io.Int.Input("overlap", default=2, min=0, max=255,
                                              tooltip="Selected images shared by adjacent windows of the same scene. This helps the LM follow movement across a window boundary, but increases repeated work. Must be smaller than max_frames. It has no effect when the scene fits in one window and never creates video cuts."),
                                 io.Custom(STORAGE_TYPE).Input("storage", optional=True,
                                              tooltip="Optional Video Run Storage control. RAM retains selected source images in CPU memory. Disk uses temporary analysis image files; Keep in output applies to generated video parts, not this analysis cache. Response JSON is saved for diagnostics in either mode.")],
                         outputs=[io.Custom(JOBS_TYPE).Output("jobs", tooltip="Window schedule and owned frame cache. Connect this same output to Scene Frame Sampler, Scene Description Collector and Save Scene Analysis."),
                                  io.Int.Output("window_count", tooltip="Total LM analysis windows across all scenes. Use this as the loop's iteration count. It can exceed scene_count when selections are split into windows."),
                                  io.Custom(STATE_TYPE).Output("empty_descriptions", tooltip="Empty text accumulator for the first loop iteration. Carry the collector's updated descriptions through subsequent iterations."),
                                  io.String.Output("report", tooltip="Window count, per-request frame limit and temporary cache location. Connect to Show Any to check the workload before describing the video.")])

    @classmethod
    def fingerprint_inputs(cls, **kwargs):
        return artifact_fingerprint()

    @classmethod
    def execute(cls, scene_plan, sampling="uniform", samples_per_scene=8, every_nth=2, max_frames=8, overlap=2, storage=None):
        jobs = prepare_scene_jobs(scene_plan, sampling, samples_per_scene, every_nth, max_frames, overlap,
                                  folder_paths.get_temp_directory(), storage)
        paths = [jobs.cache.name]
        if jobs.memory_frames is None:
            indices = {index for job in jobs.jobs for index in job["frame_indices"]}
            paths.extend(Path(jobs.cache.name) / f"{index:09d}.npy" for index in indices)
        record_artifacts(jobs, paths)
        location = "Selected frames in CPU RAM" if jobs.memory_frames is not None else f"Disk cache: {jobs.cache.name}"
        return io.NodeOutput(jobs, len(jobs.jobs), (), f"{len(jobs.jobs)} windows, at most {max_frames} frames per request. {location}")


class RvVideo_SceneFrameSampler(io.ComfyNode):
    @classmethod
    def define_schema(cls):
        return io.Schema(node_id="Scene Frame Sampler [Eclipse Nova]", display_name="Scene Frame Sampler", category=_CATEGORY,
                         description="Select a window by loop index. Pass frame_source to Smart LM Loader and context through Smart LM Prompt Pipe. No IMAGE batch is cached by the loop.",
                         inputs=[io.Custom(JOBS_TYPE).Input("jobs", tooltip="Connect the jobs output from Scene Analysis Plan. The sampler reads only the current window's selection."),
                                 io.Int.Input("index", default=0, min=0, force_input=True,
                                              tooltip="Zero-based loop index, from 0 to window_count minus 1. Connect the same index to Scene Description Collector so frames and descriptions stay matched.")],
                         outputs=[io.Custom(FRAME_SOURCE_TYPE).Output("frame_source", tooltip="Connect to Smart LM Loader's frame_source input. Together analyses the ordered selection as one sequence; Every Nth = 1 keeps all selected images. Frames are loaded and resized only for the current request."),
                                  io.String.Output("context", tooltip="Connect to Smart LM Prompt Pipe's user_prompt input. Contains matching scene/window IDs, source frame times and observation guidance. Keep it paired with this sampler's frame_source.")])

    @classmethod
    def execute(cls, jobs, index):
        return io.NodeOutput(*get_scene_job(jobs, index))


class RvVideo_SceneDescriptionCollector(io.ComfyNode):
    @classmethod
    def define_schema(cls):
        return io.Schema(node_id="Scene Description Collector [Eclipse Nova]", display_name="Scene Description Collector", category=_CATEGORY,
                         description="Collect structured scene observations or application-built scene captions. For ordinary image/H3 tasks, enable Scene JSON in Smart LM Loader. Carry only text and metadata through the loop and validate matching scene/window IDs.",
                         inputs=[io.Custom(JOBS_TYPE).Input("jobs", tooltip="Use the same Scene Analysis Plan jobs as the frame sampler. The collector checks each response against that window schedule."),
                                 io.Int.Input("index", default=0, min=0, force_input=True,
                                              tooltip="The same zero-based loop index used by Scene Frame Sampler. Windows must be collected once and in order."),
                                 io.String.Input("text", force_input=True,
                                                 tooltip="Connect Smart LM Loader's text output. Enable Scene JSON for ordinary image/H3 tasks; the loader packages their text in code. Dedicated scene tasks already return structured JSON. Keep one task throughout the loop. Missing required text or mismatched IDs stop with a recovery-file path; content review warnings preserve usable observations."),
                                 io.Custom(STATE_TYPE).Input("descriptions", tooltip="Text accumulator carried by the loop. Begin with Scene Analysis Plan's empty_descriptions, then pass the previous collector output into the next iteration.")],
                         outputs=[io.Custom(STATE_TYPE).Output("descriptions", tooltip="Accumulator including the current window. Carry it through the loop, then connect the final result to Save Scene Analysis. It stores text and metadata, not image batches.")], is_input_list=True)

    @classmethod
    def execute(cls, jobs, index, text, descriptions):
        return io.NodeOutput(collect_scene_description(jobs[0], index[0], text, descriptions[0]))


class RvVideo_SaveSceneAnalysis(io.ComfyNode):
    @classmethod
    def define_schema(cls):
        return io.Schema(node_id="Save Scene Analysis [Eclipse Nova]", display_name="Save Scene Analysis", category=_CATEGORY,
                         description="Validate complete scene coverage, merge window evidence and save a reusable versioned JSON file. Each run writes a new file in output/scene_analysis.",
                         inputs=[io.Custom(JOBS_TYPE).Input("jobs", tooltip="The jobs used by the completed analysis loop. Every scheduled window must have a collected description."),
                                 io.Custom(STATE_TYPE).Input("descriptions", tooltip="Connect the final descriptions returned after the loop completes. Incomplete or reordered results are rejected so no scene silently disappears."),
                                 io.String.Input("filename_prefix", default="reference",
                                                 tooltip="Editable filename label, without folders. It does not automatically follow the selected video's name. A UTC timestamp and unique suffix are added; files are saved under ComfyUI output/scene_analysis.")],
                         outputs=[io.Custom(ANALYSIS_TYPE).Output("analysis", tooltip="Complete measured analysis for Scene Analysis to H3. New results record motion or full description mode and preserve the model's paragraph. Motion analysis focuses on transferable movement; T2V requests appearance too. Review warnings flag usable text that may need manual editing."),
                                  io.String.Output("file", tooltip="Full path of the saved JSON. Reuse it with Load Scene Analysis to avoid repeating detection and LM descriptions."),
                                  io.String.Output("report", tooltip="Saved file path, scene/window counts and review warnings. Usable descriptions remain available for copying and manual editing even when the model includes unwanted details.")],
                         is_output_node=True)

    @classmethod
    def execute(cls, jobs, descriptions, filename_prefix="reference"):
        if not filename_prefix or Path(filename_prefix).name != filename_prefix or "\\" in filename_prefix:
            raise ValueError("Filename prefix must be a simple filename without folders")
        bundle = build_scene_analysis(jobs, descriptions)
        name = f"{filename_prefix}_{datetime.now(timezone.utc):%Y%m%d_%H%M%S}_{uuid4().hex[:8]}.json"
        path = save_scene_analysis(bundle, Path(folder_paths.get_output_directory()) / "scene_analysis" / name)
        report = f"Saved {len(bundle['scenes'])} scenes and {len(jobs.jobs)} windows to {path}. Review uncertainties before generation."
        report += scene_analysis_review_report(bundle)
        return io.NodeOutput(bundle, path, report, ui={"text": [report]})


class RvVideo_LoadSceneAnalysis(io.ComfyNode):
    @classmethod
    def define_schema(cls):
        return io.Schema(node_id="Load Scene Analysis [Eclipse Nova]", display_name="Load Scene Analysis", category=_CATEGORY,
                         description="Load a saved analysis for prompt export without rerunning scene detection or the LM. The reference video itself is not needed to read the JSON; generated cut timings still require matching source audio and trim.",
                         inputs=[io.String.Input("file", default="", multiline=False,
                                                 tooltip="Full path to a current version-2 JSON from Save Scene Analysis. Older exports without performance_prompt must be analysed again. File edits are detected on the next execution.")],
                         outputs=[io.Custom(ANALYSIS_TYPE).Output("analysis", tooltip="Validated saved analysis for Scene Analysis to H3. Match the export dropdown to its description task. To obtain T2V appearance from a new motion-only analysis, rerun Scene Description (T2V).")])

    @classmethod
    def fingerprint_inputs(cls, file):
        stat = Path(file).expanduser().stat()
        return stat.st_mtime_ns, stat.st_size

    @classmethod
    def execute(cls, file):
        return io.NodeOutput(load_scene_analysis(Path(file).expanduser()))


class RvVideo_SceneAnalysisToH3(io.ComfyNode):
    @classmethod
    def define_schema(cls):
        return io.Schema(node_id="Scene Analysis to H3 [Eclipse Nova]", display_name="Scene Analysis to H3", category=_CATEGORY,
                         description="Separate global performance from the first part and subsequent part prompts. Match appearance_mode to the analysis: exclude for Scene Motion Analysis, include for Scene Description (T2V) or Scene JSON captions. New task paragraphs pass through without appearance rewriting. Times and next_part_prompts connect to the planner; main_prompt and first_part_prompt connect to both Segmented Conditioning nodes.",
                         inputs=[io.Custom(ANALYSIS_TYPE).Input("analysis", tooltip="Connect Save Scene Analysis or Load Scene Analysis. This adapter builds generation prompts from the saved result without another LM call. Use matching source audio and trim for its cut times."),
                                 io.String.Input("performance_prompt", default=H3_PERFORMANCE_PROMPT, multiline=True,
                                                 tooltip="Direction that applies throughout the video, such as performing to the supplied audio and preserving the selected image's identity. Put scene-specific framing, poses and movement in the part prompts. This text remains as entered when appearance_mode changes."),
                                 io.Combo.Input("appearance_mode", options=list(APPEARANCE_MODES), default=APPEARANCE_MODES[0], optional=True,
                                                tooltip="Use exclude with Scene Motion Analysis for image-to-video, or include with Scene Description (T2V) and Scene JSON captions. Task paragraphs pass through unchanged; switching their policy requires a new analysis run. Older unmarked saved analyses retain appearance filtering/inclusion without inference. Adjust the global performance prompt for T2V yourself.")],
                         outputs=[io.String.Output("manual_transition_times", tooltip="Measured cut times in seconds from the trimmed reference start. Connect to the H3 Audio Timeline Planner's manual_transition_times. Timings are checked against H3's 24 FPS timeline."),
                                  io.String.Output("next_part_prompts", is_output_list=True,
                                                   tooltip="One description for each part after the first, ordered to match the cut times. Connect to the planner's technical_cut_instruction. These describe the part's framing and movement; timing stays in the planner."),
                                  io.String.Output("main_prompt", tooltip="Global performance direction. Connect to prompts on both base and extension Segmented Conditioning nodes. It applies to every part."),
                                  io.String.Output("first_part_prompt", tooltip="Specific direction for the opening part only, until the first planned cut. Connect to first_part_prompt on both base and extension Segmented Conditioning nodes."),
                                  io.String.Output("report", tooltip="Part/prompt counts, selected appearance mode and content review warnings. Prompts with unwanted details remain available to copy and edit manually. For N scenes, expect one first-part prompt and N minus 1 subsequent prompts.")])

    @classmethod
    def execute(cls, analysis, performance_prompt=H3_PERFORMANCE_PROMPT, appearance_mode=APPEARANCE_MODES[0]):
        times, parts, main, first = h3_scene_part_inputs(analysis, performance_prompt, appearance_mode)
        return io.NodeOutput(times, parts, main, first,
                             f"{len(analysis['scenes'])} parts: one global prompt, one first-part prompt and {len(parts)} subsequent part prompts; {appearance_mode}. Cut times and observations are unchanged."
                             + scene_analysis_review_report(analysis))
