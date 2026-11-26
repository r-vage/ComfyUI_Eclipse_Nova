"""Blend adjacent H3 directions while encoding both with the incoming clip's pictures."""
import torch
import torch.nn.functional as F


class _TransitionClip:
    def __init__(self, clip, previous, current, percent):
        self.clip = clip
        self.previous = previous
        self.current = current
        self.weight = percent / 100

    def tokenize(self, text, **media):
        # Native Ref2VA and the segmented conditioner may prepend a picture-role sentence.
        prefix = text.removesuffix(self.current) if self.current and text.endswith(self.current) else ""
        old = self.previous if "<picture " in self.previous.casefold() else prefix + self.previous
        prior = self.clip.tokenize(old, **media)
        return (None if self.weight == 1 else self.clip.tokenize(text, **media)), prior

    def encode_from_tokens_scheduled(self, tokens):
        new_tokens, old_tokens = tokens
        old = self.clip.encode_from_tokens_scheduled(old_tokens)
        if self.weight == 1:
            return old
        new = self.clip.encode_from_tokens_scheduled(new_tokens)
        result = []
        for (dest, meta), (prior, _) in zip(new, old, strict=True):
            length = max(dest.shape[1], prior.shape[1])
            current = F.pad(dest, (0, 0, 0, length - dest.shape[1]))
            previous = F.pad(prior.to(dest), (0, 0, 0, length - prior.shape[1]))
            mixed = torch.lerp(current, previous, self.weight)
            meta = meta.copy()
            tags = meta.get("minimax_token_tags")
            if tags is not None:
                tags = F.pad(tags, (0, length - tags.shape[-1]), value=1)
                meta["minimax_token_tags"] = tags
                mixed = torch.where(tags.to(dest.device).reshape(1, -1, 1) == 0, current, mixed)
            result.append([mixed, meta])
        return result


def transition_clip(clip, previous, current, percent):
    if not percent or not previous or previous == current:
        return clip
    return _TransitionClip(clip, previous, current, percent)
