import unittest
from types import SimpleNamespace

from pydantic import BaseModel

from Backend.rag_app.core.config import Settings
from Backend.rag_app.embedding_generation.service import AzureOpenAIService


class FakeEmbeddings:
    def __init__(self) -> None:
        self.calls = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        data = [
            SimpleNamespace(index=index, embedding=[float(index), 1.0])
            for index, _ in enumerate(kwargs["input"])
        ]
        return SimpleNamespace(data=data)


class StructuredPayload(BaseModel):
    value: str


class FakeParser:
    def parse(self, **kwargs):
        self.kwargs = kwargs
        message = SimpleNamespace(parsed=StructuredPayload(value="ok"))
        return SimpleNamespace(choices=[SimpleNamespace(message=message)])


class AzureOpenAIServiceTests(unittest.TestCase):
    def test_embeddings_are_batched(self) -> None:
        fake_embeddings = FakeEmbeddings()
        fake_client = SimpleNamespace(embeddings=fake_embeddings)
        settings = Settings(_env_file=None, embedding_batch_size=2, embedding_dimensions=2)
        service = AzureOpenAIService(settings, client=fake_client)

        result = service.embed_documents(["one", "two", "three"])

        self.assertEqual(len(fake_embeddings.calls), 2)
        self.assertEqual(len(result), 3)
        self.assertEqual(fake_embeddings.calls[0]["dimensions"], 2)

    def test_empty_embedding_input_is_rejected(self) -> None:
        fake_client = SimpleNamespace(embeddings=FakeEmbeddings())
        service = AzureOpenAIService(Settings(_env_file=None), client=fake_client)
        with self.assertRaises(ValueError):
            service.embed_query("  ")

    def test_structured_completion_uses_pydantic_response_model(self) -> None:
        parser = FakeParser()
        fake_client = SimpleNamespace(
            embeddings=FakeEmbeddings(),
            beta=SimpleNamespace(chat=SimpleNamespace(completions=parser)),
        )
        service = AzureOpenAIService(Settings(_env_file=None), client=fake_client)

        result = service.complete_structured(
            [{"role": "user", "content": "Return a value"}],
            StructuredPayload,
        )

        self.assertEqual(result.value, "ok")
        self.assertIs(parser.kwargs["response_format"], StructuredPayload)


if __name__ == "__main__":
    unittest.main()
