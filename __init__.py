# ComfyUI_Eclipse Extension Loader
# Initializes and loads all custom nodes for ComfyUI_Eclipse using the ComfyUI V3 extension API.
WEB_DIRECTORY = "./js"

import sys

# Prevent shadowing of ComfyUI's top-level utils package by comfy/utils.py when nodes.py is imported first.
if "utils" not in sys.modules:
    try:
        import utils  # type: ignore
    except ImportError:
        pass

from .core import version
from .core.logger import log, cstr

log.msg("", f"Version: {version}")

# Initialize Eclipse folder structure
from .core.migration import run_migrations

run_migrations()

# Initialize server endpoints
try:
    from .core.server_endpoints import initialize_endpoints

    initialize_endpoints()
except Exception as e:
    log.warning("", f"Failed to initialize server endpoints: {e}")

# V3 Extension Registration
from comfy_api.latest import ComfyExtension, io  # type: ignore


class EclipseExtension(ComfyExtension):
    async def get_node_list(self) -> list[type[io.ComfyNode]]:
        # Conversion nodes
        from .py.RvConversion_ConcatMulti import RvConversion_ConcatMulti
        from .py.RvConversion_ConvertPrimitive import RvConversion_ConvertPrimitive
        from .py.RvConversion_ToBatch import RvConversion_ToBatch
        from .py.RvConversion_RIFEMultiplier import RvConversion_RIFEMultiplier
        from .py.RvConversion_ToList import RvConversion_ToList
        from .py.RvConversion_ImageConvert import RvConversion_ImageConvert
        from .py.RvConversion_IndicesToList import RvConversion_IndicesToList
        from .py.RvConversion_Join import RvConversion_Join
        from .py.RvConversion_MergeStrings import RvConversion_MergeStrings
        from .py.RvConversion_StringFromList import RvConversion_StringFromList

        # Folder nodes
        from .py.RvFolder_AddFolder import RvFolder_AddFolder
        from .py.RvFolder_FilenamePrefix import RvFolder_FilenamePrefix
        from .py.RvFolder_SmartFolder import RvFolder_SmartFolder

        # Image nodes
        from .py.RvImage_Load import RvImage_Load
        from .py.RvImage_LoadFiles import RvImage_LoadFiles
        from .py.RvImage_PreviewDomStop import RvImage_PreviewDomStop
        from .py.RvImage_Selector import RvImage_Selector
        from .py.RvImage_Comparer import RvImage_Comparer
        from .py.RvImage_CropByMask import RvImage_CropByMask
        from .py.RvImage_Resize import RvImage_Resize
        from .py.RvImage_Save import RvImage_Save
        from .py.RvImage_Preview_SEGS_Simple import RvImage_Preview_SEGS_Simple
        from .py.RvMask_ToSEGS import RvMask_ToSEGS
        from .py.RvSampler_DetailerForEach import RvSampler_DetailerForEach
        from .py.RvImage_TileAssembly import RvImage_TileAssembly
        from .py.RvImage_TileDecodeAssembly import RvImage_TileDecodeAssembly
        from .py.RvImage_TileSplit import RvImage_TileSplit
        from .py.RvImage_TextImageWithFX import RvImage_TextImageWithFX
        from .py.RvImage_ImageWithFX import RvImage_ImageWithFX
        from .py.RvImage_AlignSize import RvImage_AlignSize
        from .py.RvImage_GetLast import RvImage_GetLast
        from .py.RvImage_GetFirst import RvImage_GetFirst
        from .py.RvImage_BatchSlice import RvImage_BatchSlice
        from .py.RvImage_ReviewFilter import RvImage_ReviewFilter
        from .py.RvImage_BatchInterleave import RvImage_BatchInterleave
        from .py.RvImage_BatchStrip import RvImage_BatchStrip
        from .py.RvImage_BatchExtendWithOverlap import RvImage_BatchExtendWithOverlap
        from .py.RvImage_BatchExtendWithRife import RvImage_BatchExtendWithRife
        from .py.RvImage_InsetCrop import RvImage_InsetCrop
        from .py.RvImage_FilterAdjustmentsAdvanced import RvImage_FilterAdjustmentsAdvanced

        # Audio nodes (diffusion loaders live in ComfyUI_SmartModelLoader)
        from .py.RvVideo_RenderLyricCaptions import RvVideo_RenderLyricCaptions
        from .py.RvVideo_RenderLyricCaptionsPipe import RvVideo_RenderLyricCaptionsPipe
        from .py.RvAudio_LoadAudio import RvAudio_LoadAudio
        from .py.RvAudio_TranscribeAudio import RvAudio_TranscribeAudio
        from .py.RvAudio_SystemAudioRecorder import RvAudio_SystemAudioRecorder

        # Logic nodes
        from .py.RvLogic_Float import RvLogic_Float
        from .py.RvLogic_Integer_Gen import RvLogic_IntegerGen
        from .py.RvLogic_None import RvLogic_None
        from .py.RvLogic_Seed import RvLogic_Seed
        from .py.RvLogic_DualSeed import RvLogic_DualSeed

        # Sampler nodes
        from .py.RvSampler_KSamplerKargim import RvSampler_KSamplerKargim
        from .py.RvSampler_KSamplerAdvanced import RvSampler_KSamplerAdvanced
        from .py.RvPipe_IO_KSampler import RvPipe_IO_KSampler

        # Pipe IO nodes
        from .py.RvPipe_IO_LyricCaptions import RvPipe_IO_LyricCaptions
        from .py.RvPipe_IO_12CH_Any import RvPipe_IO_12CH_Any
        from .py.RvPipe_IO_24CH_Any import RvPipe_IO_24CH_Any
        from .py.RvPipe_IO_36CH_Any import RvPipe_IO_36CH_Any
        from .py.RvPipe_IO_Context_Image import RvPipe_IO_Context_Image
        from .py.RvPipe_IO_Context_Video import RvPipe_IO_Context_Video
        from .py.RvPipe_IO_Context_WanVideoWrapper import (
            RvPipe_IO_Context_WanVideoWrapper,
        )
        from .py.RvPipe_IO_LoadImage import RvPipe_IO_LoadImage
        from .py.RvPipe_IO_Generation_Data import RvPipe_IO_Generation_Data
        from .py.RvPipe_IO_Generation_Data_Gated import RvPipe_IO_Generation_Data_Gated
        from .py.RvPipe_IO_Sampler_Settings import RvPipe_IO_Sampler_Settings
        from .py.RvPipe_IO_SliceDice import RvPipe_IO_SliceDice

        # Pipe Out nodes
        from .py.RvPipe_Out_SmartFolder import RvPipe_Out_SmartFolder

        # Basic Pipe nodes
        # Router nodes
        from .py.RvRouter_Any_DualSwitch import RvRouter_Any_DualSwitch
        from .py.RvRouter_Any_DualSwitch_purge import RvRouter_Any_DualSwitch_purge
        from .py.RvRouter_Any_MultiSwitch import RvRouter_Any_MultiSwitch
        from .py.RvRouter_Any_MultiSwitchMixed import RvRouter_Any_MultiSwitchMixed
        from .py.RvRouter_Any_MultiSwitch_purge import RvRouter_Any_MultiSwitch_purge
        from .py.RvRouter_Any_MultiSwitch_lazy import RvRouter_Any_MultiSwitch_lazy
        from .py.RvRouter_Any_MultiSwitch_lazy_purge import (
            RvRouter_Any_MultiSwitch_lazy_purge,
        )
        from .py.RvRouter_Any_Passer import RvRouter_Any_Passer
        from .py.RvRouter_Any_Passer_purge import RvRouter_Any_Passer_purge
        from .py.RvRouter_Boolean_Passer import RvRouter_Boolean_Passer
        from .py.RvRouter_Float_Passer import RvRouter_Float_Passer
        from .py.RvRouter_Int_Passer import RvRouter_Int_Passer
        from .py.RvRouter_String_Passer import RvRouter_String_Passer
        from .py.RvRouter_Model_Passer import RvRouter_Model_Passer
        from .py.RvRouter_Clip_Passer import RvRouter_Clip_Passer
        from .py.RvRouter_Vae_Passer import RvRouter_Vae_Passer
        from .py.RvRouter_Segs_Passer import RvRouter_Segs_Passer
        from .py.RvRouter_Audio_Passer import RvRouter_Audio_Passer
        from .py.RvRouter_BasicPipe_Passer import RvRouter_BasicPipe_Passer
        from .py.RvRouter_Conditioning_Passer import RvRouter_Conditioning_Passer
        from .py.RvRouter_ControlNet_Passer import RvRouter_ControlNet_Passer
        from .py.RvRouter_DetailerPipe_Passer import RvRouter_DetailerPipe_Passer
        from .py.RvRouter_Image_Passer import RvRouter_Image_Passer
        from .py.RvRouter_Latent_Passer import RvRouter_Latent_Passer
        from .py.RvRouter_Mask_Passer import RvRouter_Mask_Passer
        from .py.RvRouter_WanVideoModel_Passer import RvRouter_WanVideoModel_Passer
        from .py.RvRouter_Pipe_Passer import RvRouter_Pipe_Passer
        from .py.RvRouter_IfElse import RvRouter_IfElse
        from .py.RvImage_LoopImageSelector import RvImage_LoopImageSelector

        # Settings nodes
        from .py.RvSettings_ControlNetUnionType import RvSettings_ControlNetUnionType
        from .py.RvSettings_ResolutionPipe import RvSettings_ResolutionPipe
        from .py.RvSettings_SmartSamplerSettings import RvSettings_SmartSamplerSettings

        # Character reference nodes
        from .py.RvImage_CharacterReferenceSelect import RvImage_CharacterReferenceSelect
        from .py.RvImage_CharacterPanels import (
            RvImage_CharacterReferencePrepare,
            RvImage_CharacterReferencePack,
            RvImage_CharacterSheetPack,
            RvImage_CharacterSheetSplit,
        )

        # Text nodes
        from .py.RvText_CharacterShotPlanner import RvText_CharacterShotPlanner
        from .py.RvText_DanbooruPromptForge import RvText_DanbooruPromptForge
        from .py.RvText_ShotPlanSlice import RvText_ShotPlanSlice
        from .py.RvText_DeDuplicate import RvText_DeDuplicate
        from .py.RvText_DualText import RvText_DualText
        from .py.RvText_MarkdownNote import RvText_MarkdownNote
        from .py.RvText_Multiline import RvText_Multiline
        from .py.RvText_PromptStyler import RvText_PromptStyler
        from .py.RvText_ReadPromptFiles import RvText_ReadPromptFiles
        from .py.RvText_ReplaceString import RvText_ReplaceString
        from .py.RvText_SavePrompt import RvText_SavePrompt
        from .py.RvText_SmartPrompt import RvText_SmartPrompt
        from .py.RvText_WildcardProcessorList import RvText_WildcardProcessorList

        # Tools nodes
        from .py.RvTools_FastModeToggle import RvTools_FastModeToggle
        from .py.RvTools_FastModeToggleNative import RvTools_FastModeToggleNative
        from .py.RvTools_FastModeSwitcher import RvTools_FastModeSwitcher
        from .py.RvTools_NodeModeRepeater import RvTools_NodeModeRepeater
        from .py.RvTools_ModeRelay import RvTools_ModeRelay
        from .py.RvTools_ModeBridgeSet import RvTools_ModeBridgeSet
        from .py.RvTools_ModeBridgeGet import RvTools_ModeBridgeGet
        from .py.RvVideo_LoopCalc import RvVideo_LoopCalc
        from .py.RvAudio_LoopCalc import RvAudio_LoopCalc
        from .py.RvVideo_LoopKeepCalc import RvVideo_LoopKeepCalc
        from .py.RvAudio_LoopAlignSilence import RvAudio_LoopAlignSilence
        from .py.RvVideo_WanLipSyncConditioning import RvVideo_WanLipSyncConditioning
        from .py.RvVideo_WanLipSyncPlanStep import RvVideo_WanLipSyncPlanStep
        from .py.RvVideo_WanLipSyncTimelinePlanner import RvVideo_WanLipSyncTimelinePlanner
        from .py.RvVideo_MiniMaxH3Panels import (
            RvVideo_MiniMaxH3SegmentedTimelinePanel,
            RvVideo_MiniMaxH3SegmentedStepPanel, RvVideo_MiniMaxH3SegmentedConditioningPanel,
        )
        from .py.RvVideo_TrimToShortest import RvVideo_TrimToShortest
        from .py.RvVideo_Preview import RvVideo_Preview
        from .py.RvVideo_FrameTimeline import (
            RvVideo_TimelineLoopGate,
            RvVideo_DecodeAppendTimeline,
            RvVideo_TrimTimeline,
        )
        from .py.RvVideo_SaveData import RvVideo_SaveData
        from .py.RvVideo_Load import RvVideo_Load
        from .py.RvVideo_Split import RvVideo_Split
        from .py.RvVideo_Upscale import RvVideo_Upscale
        from .py.RvVideo_FrameConsistency import RvVideo_FrameConsistency
        from .py.RvTools_ResolutionScale import RvTools_ResolutionScale
        from .py.RvTools_ShowAny import RvTools_ShowAny
        from .py.RvTools_ShowAnyStop import RvTools_ShowAnyStop
        from .py.RvTools_Stop import RvTools_Stop

        node_list: list[type[io.ComfyNode]] = [
            # Conversion
            RvConversion_ConcatMulti,
            RvConversion_ConvertPrimitive,
            RvConversion_ToBatch,
            RvConversion_RIFEMultiplier,
            RvConversion_ToList,
            RvConversion_ImageConvert,
            RvConversion_IndicesToList,
            RvConversion_Join,
            RvConversion_MergeStrings,
            RvConversion_StringFromList,
            # Folder
            RvFolder_AddFolder,
            RvFolder_FilenamePrefix,
            RvFolder_SmartFolder,
            # Image
            RvImage_Load,
            RvImage_LoadFiles,
            RvImage_PreviewDomStop,
            RvImage_Selector,
            RvImage_Comparer,
            RvImage_CropByMask,
            RvImage_Resize,
            RvImage_Save,
            RvImage_Preview_SEGS_Simple,
            RvMask_ToSEGS,
            RvSampler_DetailerForEach,
            RvImage_TileAssembly,
            RvImage_TileDecodeAssembly,
            RvImage_TileSplit,
            RvImage_TextImageWithFX,
            RvImage_ImageWithFX,
            RvImage_AlignSize,
            RvImage_GetLast,
            RvImage_GetFirst,
            RvImage_BatchSlice,
            RvImage_ReviewFilter,
            RvImage_BatchInterleave,
            RvImage_BatchStrip,
            RvImage_BatchExtendWithOverlap,
            RvImage_BatchExtendWithRife,
            RvImage_InsetCrop,
            RvImage_FilterAdjustmentsAdvanced,
            # Audio
            RvVideo_RenderLyricCaptions,
            RvVideo_RenderLyricCaptionsPipe,
            RvAudio_LoadAudio,
            RvAudio_TranscribeAudio,
            RvAudio_SystemAudioRecorder,
            # Logic
            RvLogic_Float,
            RvLogic_IntegerGen,
            RvLogic_None,
            RvLogic_Seed,
            RvLogic_DualSeed,
            # Sampler
            RvSampler_KSamplerKargim,
            RvSampler_KSamplerAdvanced,
            RvPipe_IO_KSampler,
            # Pipe IO
            RvPipe_IO_LyricCaptions,
            RvPipe_IO_12CH_Any,
            RvPipe_IO_24CH_Any,
            RvPipe_IO_36CH_Any,
            RvPipe_IO_Context_Image,
            RvPipe_IO_Context_Video,
            RvPipe_IO_Context_WanVideoWrapper,
            RvPipe_IO_LoadImage,
            RvPipe_IO_Generation_Data,
            RvPipe_IO_Generation_Data_Gated,
            RvPipe_IO_Sampler_Settings,
            RvPipe_IO_SliceDice,
            # Pipe Out
            RvPipe_Out_SmartFolder,
            # Basic Pipe
            # Router
            RvRouter_Any_DualSwitch,
            RvRouter_Any_DualSwitch_purge,
            RvRouter_Any_MultiSwitch,
            RvRouter_Any_MultiSwitchMixed,
            RvRouter_Any_MultiSwitch_purge,
            RvRouter_Any_MultiSwitch_lazy,
            RvRouter_Any_MultiSwitch_lazy_purge,
            RvRouter_Any_Passer,
            RvRouter_Any_Passer_purge,
            RvRouter_Boolean_Passer,
            RvRouter_Float_Passer,
            RvRouter_Int_Passer,
            RvRouter_String_Passer,
            RvRouter_Model_Passer,
            RvRouter_Clip_Passer,
            RvRouter_Vae_Passer,
            RvRouter_Segs_Passer,
            RvRouter_Audio_Passer,
            RvRouter_BasicPipe_Passer,
            RvRouter_Conditioning_Passer,
            RvRouter_ControlNet_Passer,
            RvRouter_DetailerPipe_Passer,
            RvRouter_Image_Passer,
            RvRouter_Latent_Passer,
            RvRouter_Mask_Passer,
            RvRouter_WanVideoModel_Passer,
            RvRouter_Pipe_Passer,
            RvRouter_IfElse,
            RvImage_LoopImageSelector,
            # Settings
            RvSettings_ControlNetUnionType,
            RvSettings_ResolutionPipe,
            RvSettings_SmartSamplerSettings,
            # Character references
            RvImage_CharacterReferenceSelect,
            RvImage_CharacterReferencePrepare,
            RvImage_CharacterReferencePack,
            RvImage_CharacterSheetPack,
            RvImage_CharacterSheetSplit,
            # Text
            RvText_CharacterShotPlanner,
            RvText_ShotPlanSlice,
            RvText_DanbooruPromptForge,
            RvText_DeDuplicate,
            RvText_DualText,
            RvText_MarkdownNote,
            RvText_Multiline,
            RvText_PromptStyler,
            RvText_ReadPromptFiles,
            RvText_ReplaceString,
            RvText_SavePrompt,
            RvText_SmartPrompt,
            RvText_WildcardProcessorList,
            # Tools
            RvTools_FastModeToggle,
            RvTools_FastModeToggleNative,
            RvTools_FastModeSwitcher,
            RvTools_NodeModeRepeater,
            RvTools_ModeRelay,
            RvTools_ModeBridgeSet,
            RvTools_ModeBridgeGet,
            RvVideo_LoopCalc,
            RvAudio_LoopCalc,
            RvVideo_LoopKeepCalc,
            RvAudio_LoopAlignSilence,
            RvVideo_WanLipSyncTimelinePlanner,
            RvVideo_WanLipSyncPlanStep,
            RvVideo_WanLipSyncConditioning,
            RvVideo_MiniMaxH3SegmentedTimelinePanel,
            RvVideo_MiniMaxH3SegmentedStepPanel,
            RvVideo_MiniMaxH3SegmentedConditioningPanel,
            RvVideo_TrimToShortest,
            RvVideo_Preview,
            RvVideo_DecodeAppendTimeline,
            RvVideo_TrimTimeline,
            RvVideo_TimelineLoopGate,
            RvVideo_SaveData,
            RvVideo_Load,
            RvVideo_Split,
            RvVideo_Upscale,
            RvVideo_FrameConsistency,
            RvTools_ResolutionScale,
            RvTools_ShowAny,
            RvTools_ShowAnyStop,
            RvTools_Stop,
        ]

        return node_list


async def comfy_entrypoint() -> EclipseExtension:
    return EclipseExtension()
