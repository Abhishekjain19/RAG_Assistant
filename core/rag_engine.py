from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser
from langchain_core.runnables import RunnableLambda, RunnablePassthrough

from core.llm import get_llm, invoke_with_retry
from core.vector_store import build_vector_store, load_vector_store, get_retriever


def format_docs(docs):
    return "\n\n".join([doc.page_content for doc in docs])


def _rag_prompt():
    return ChatPromptTemplate.from_messages(
        [
            (
                "system",
                """You are an expert meeting assistant.

Answer the user's question using the meeting transcript context provided below.

Rules:
1. Use the transcript context as the primary and authoritative source.
2. Understand the semantic meaning and intent of the user's question.
3. Do NOT require the question to use the same words or phrasing as the transcript.
4. Treat paraphrases, synonyms, abbreviations, different grammatical forms, and indirect references as equivalent when they clearly refer to the same information.
5. If the transcript contains information that logically answers the question, provide that answer even if the exact question is not explicitly stated in the transcript.
6. Combine information from multiple transcript passages when necessary to answer the question.
7. Pay close attention to names, numbers, dates, roles, titles, acronyms, decisions, responsibilities, deadlines, and other specific details.
8. Do not invent information or use outside knowledge that is not supported by the transcript.
9. If the context is related to the question but does not contain enough information to determine the answer, say:
   "I could not find enough information to answer this from the meeting transcript."
10. Only use that fallback when the required information genuinely cannot be determined from the provided context.
11. Give the answer directly and concisely. Do not explain your retrieval process.

Meeting transcript context:
{context}
""",
            ),
            ("human", "{question}"),
        ]
    )


def build_rag_chain(transcript: str):
    vector_store = build_vector_store(transcript)
    retriever = get_retriever(
        vector_store,
        k=6,
        search_type="similarity",
    )
    llm = get_llm()
    return (
        {
            "context": retriever | RunnableLambda(format_docs),
            "question": RunnablePassthrough(),
        }
        | _rag_prompt()
        | llm
        | StrOutputParser()
    )

def load_rag_chain():
    vector_store = load_vector_store()

    retriever = get_retriever(
        vector_store,
        k=6,
        search_type="similarity"
    )

    llm = get_llm()

    return (
        {
            "context": retriever | RunnableLambda(format_docs),
            "question": RunnablePassthrough(),
        }
        | _rag_prompt()
        | llm
        | StrOutputParser()
    )

def ask_question(rag_chain, question: str) -> str:
    print(f"Question : {question}")
    answer = invoke_with_retry(rag_chain, question)
    print(f"answer :{answer}")
    return answer
