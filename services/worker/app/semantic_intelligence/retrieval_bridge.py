from typing import Dict, Any


class RetrievalBridge:
    """
    Retrieval Bridge（检索桥接层）

    Semantic Intelligence（语义智能层）
            ↓
    RagRetriever（RAG检索器）
    """

    def __init__(
        self,
        rag_retriever
    ):
        self.rag_retriever = rag_retriever



    def retrieve(
        self,
        rag_request: Dict[str, Any]
    ) -> list[dict]:

        """
        Execute Retrieval（执行检索）
        """


        params = self._build_retriever_params(
            rag_request
        )

        return self.rag_retriever.search(
            **params
        )


    def retrieve_context(
        self,
        rag_request: Dict[str, Any]
    ):

        """
        Execute Retrieval and return formal RagContext.
        """

        params = self._build_retriever_params(
            rag_request
        )

        return self.rag_retriever.build_context_payload(
            **params
        )


    @staticmethod
    def _build_retriever_params(
        rag_request: Dict[str, Any]
    ) -> dict[str, Any]:

        query = rag_request.get(
            "query",
            ""
        )

        top_k = rag_request.get(
            "top_k",
            10
        )

        metadata_filter = rag_request.get(
            "metadata_filter",
            {}
        )

        target_dimension = (
            metadata_filter.get(
                "dimension"
            )
        )

        return {
            "query": query,
            "top_k": top_k,
            "transcript": rag_request.get(
                "transcript"
            ),
            "meeting_type": rag_request.get(
                "meeting_type"
            ),
            "meeting_type_confidence": rag_request.get(
                "meeting_type_confidence"
            ),
            "target_dimension": target_dimension,
        }
