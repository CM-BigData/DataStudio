from __future__ import annotations

from typing import Any


class RetrievalQAAccessor:
    def setup_embeddings(self, config: dict[str, Any]) -> None:
        """Set up embeddings required for QA retrieval

        Business logic:
            1. Define the embedding setup entry point
            2. Allow concrete implementations to load vector models
            3. Let the base class only persist config by default

        Args:
            config (dict[str, Any]): Embedding configuration.

        Returns:
            None: The base implementation only records config.

        Examples:
            >>> accessor = RetrievalQAAccessor(); accessor.setup_embeddings({'model': 'local'}); accessor.embedding_config['model']
            'local'
        """
        self.embedding_config = dict(config)  # Embedding config used by the QA retrieval pipeline.

    def generate_questions(self, text: str, count: int) -> list[str]:
        """Generate questions from text

        Business logic:
            1. Define the question-generation interface
            2. Accept source text and the target count
            3. Provide a lightweight local fallback in the base class

        Args:
            text (str): Input text.
            count (int): Target number of questions.

        Returns:
            list[str]: Question list.

        Examples:
            >>> RetrievalQAAccessor().generate_questions('Alpha beta.', 1)
            ['What is the key point of Alpha beta?']
        """
        cleaned = _first_sentence(text)
        if not cleaned:  # Empty text cannot produce answerable questions.
            return []
        return [f"What is the key point of {cleaned}?" for _ in range(max(0, count))]

    def answer(self, text: str, question: str) -> str:
        """Generate an answer from text and question

        Business logic:
            1. Define the retrieval answer interface
            2. Use the first sentence as the local fallback answer in the base class
            3. Return answer text that can be written by the mapper

        Args:
            text (str): Retrieval context text.
            question (str): Question.

        Returns:
            str: Answer text.

        Examples:
            >>> RetrievalQAAccessor().answer('Alpha beta.', 'Q')
            'Alpha beta.'
        """
        return _first_sentence(text)


class FakeRetrievalQAAccessor(RetrievalQAAccessor):
    def __init__(self, questions: list[str] | None = None, answers: dict[str, str] | None = None) -> None:
        """Initialize the fake QA retrieval accessor

        Business logic:
            1. Store a fixed list of questions
            2. Store the question-to-answer mapping
            3. Provide a network-free path for narrow workflow tests

        Args:
            questions (list[str] | None): Fixed question list.
            answers (dict[str, str] | None): Fixed answer mapping.

        Returns:
            None: Initializers do not return data.

        Examples:
            >>> FakeRetrievalQAAccessor(['Q'], {'Q': 'A'}).answer('x', 'Q')
            'A'
        """
        self.questions = questions or []  # Fixed questions returned predictably by the fake accessor.
        self.answers = answers or {}  # Fixed answers indexed by question text for fake responses.
        self.embedding_config: dict[str, Any] = {}  # Embedding config captured from test inputs.

    def setup_embeddings(self, config: dict[str, Any]) -> None:
        """Record fake embedding configuration

        Business logic:
            1. Accept embedding configuration
            2. Save it on the instance
            3. Keep the interface aligned with the real accessor

        Args:
            config (dict[str, Any]): Embedding configuration.

        Returns:
            None: Only records configuration.

        Examples:
            >>> fake = FakeRetrievalQAAccessor(); fake.setup_embeddings({'model': 'x'}); fake.embedding_config['model']
            'x'
        """
        self.embedding_config = dict(config)  # Embedding config for the fake retrieval pipeline.

    def generate_questions(self, text: str, count: int) -> list[str]:
        """Return a fixed list of questions

        Business logic:
            1. Use configured questions
            2. Truncate by count
            3. Fall back to base-class local generation when unset

        Args:
            text (str): Input text.
            count (int): Target number of questions.

        Returns:
            list[str]: Question list.

        Examples:
            >>> FakeRetrievalQAAccessor(['Q1', 'Q2']).generate_questions('x', 1)
            ['Q1']
        """
        if self.questions:  # Prefer fixed questions when configured to keep results stable.
            return self.questions[:count]
        return super().generate_questions(text, count)

    def answer(self, text: str, question: str) -> str:
        """Return a fixed answer

        Business logic:
            1. Prefer the mapped answer for the question
            2. Fall back to the base-class answer when missing
            3. Return stable text

        Args:
            text (str): Input text.
            question (str): Question.

        Returns:
            str: Answer text.

        Examples:
            >>> FakeRetrievalQAAccessor(['Q'], {'Q': 'A'}).answer('x', 'Q')
            'A'
        """
        return self.answers.get(question, super().answer(text, question))


def _first_sentence(text: str) -> str:
    """Extract the first readable sentence from text

    Business logic:
        1. Collapse whitespace
        2. Cut at common Chinese or English sentence-ending punctuation
        3. Return either an empty string or the first sentence

    Args:
        text (str): Input text.

    Returns:
        str: First sentence text.

    Examples:
        >>> _first_sentence(' Alpha beta. Gamma.')
        'Alpha beta.'
    """
    cleaned = " ".join(str(text or "").split())
    if not cleaned:  # Empty text has no extractable first sentence.
        return ""
    for index, char in enumerate(cleaned):  # Find the first sentence boundary using Chinese and English punctuation.
        if char in "。！？.!?":  # Return the first sentence including its ending punctuation.
            return cleaned[: index + 1].strip()
    return cleaned
