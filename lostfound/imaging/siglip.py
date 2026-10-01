"""Adaptador opcional SigLIP2; la carga del modelo es explícita."""
import math

from .preprocessing import prepare_image

MODEL = "google/siglip2-base-patch16-224"


class SiglipEncoder:
    def __init__(self, model=MODEL, revision='main'):
        try:
            import torch
            from transformers import AutoModel, AutoProcessor
        except ImportError as exc:
            raise RuntimeError('Instala el extra vision del proyecto en un entorno virtual para usar visión') from exc
        self.torch = torch
        self.model_id = model
        self.model = AutoModel.from_pretrained(model, revision=revision).eval()
        self.revision = getattr(self.model.config, '_commit_hash', None) or revision
        self.processor = AutoProcessor.from_pretrained(model, revision=self.revision)

    def vector(self, features):
        values = features[0].detach().cpu().float().tolist()
        norm = math.sqrt(sum(x * x for x in values))
        if norm == 0 or not math.isfinite(norm):
            raise ValueError('Embedding no válido')
        return [x / norm for x in values]

    def text(self, text):
        # Refuse silent truncation: the user can shorten the visual description.
        if len(self.processor.tokenizer(text.lower())['input_ids']) > 64:
            raise ValueError('La descripción supera los 64 tokens del modelo visual; acórtala')
        inputs = self.processor(text=[text.lower()], padding='max_length',
                                max_length=64, return_tensors='pt')
        with self.torch.inference_mode():
            return self.vector(self.model.get_text_features(**inputs))

    def image(self, path):
        image, quality = prepare_image(path)
        inputs = self.processor(images=image, return_tensors='pt')
        with self.torch.inference_mode():
            return self.vector(self.model.get_image_features(**inputs)), quality
