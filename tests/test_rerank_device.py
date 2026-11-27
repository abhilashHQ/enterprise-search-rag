"""Needs torch: uv run --no-sync --extra app --extra models pytest tests/test_rerank_device.py"""

from types import SimpleNamespace

import torch

from entsearch.retrieval import rerank


class FakeTok:
    def __init__(self, moved_to):
        self.moved_to = moved_to

    def convert_tokens_to_ids(self, t):
        return {"no": 0, "yes": 1}[t]

    def encode(self, text, add_special_tokens=False):
        return [2] * min(len(text), 5)

    def pad(self, batch, padding, return_tensors):
        moved_to = self.moved_to

        class Enc(dict):
            def to(self, device):
                moved_to.append(device)
                return self

        return Enc(input_ids=torch.tensor(batch["input_ids"]))


class FakeModel:
    def eval(self):
        return self

    def __call__(self, input_ids, logits_to_keep):
        logits = torch.zeros(len(input_ids), 1, 3)
        logits[:, -1, 1] = 2.0
        return SimpleNamespace(logits=logits)


def load(monkeypatch, **kw):
    loaded, moved_to = {}, []
    monkeypatch.setattr(rerank.AutoTokenizer, "from_pretrained", lambda *a, **k: FakeTok(moved_to))
    monkeypatch.setattr(rerank.AutoModelForCausalLM, "from_pretrained", lambda *a, **k: loaded.update(k) or FakeModel())
    return rerank.Reranker(**kw), loaded, moved_to


def test_cpu_loads_fp32_weights_and_inputs_on_cpu(monkeypatch):
    r, loaded, moved_to = load(monkeypatch, device="cpu")
    scores = r.score("q", ["a", "bb"])
    assert loaded["device_map"] == "cpu" and loaded["dtype"] == torch.float32
    assert set(moved_to) == {"cpu"} and scores.shape == (2,)


def test_cuda_stays_the_fp16_default(monkeypatch):
    _, loaded, _ = load(monkeypatch)
    assert loaded["device_map"] == "cuda" and loaded["dtype"] == torch.float16
