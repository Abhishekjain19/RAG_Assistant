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
                """You are an expert meeting assistant. Answer the user's question 
based ONLY on the meeting transcript context provided below.

If the answer is not found in the context, say: 
"I could not find this information in the meeting transcript."

Always be concise and precise. If quoting someone, mention it clearly.

Context from meeting transcript:
{context}""",
            ),
            ("human", "{question}"),
        ]
    )


def build_rag_chain(transcript: str):
    vector_store = build_vector_store(transcript)
    retriever = get_retriever(vector_store, k=4)
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
    retriever = get_retriever(vector_store)
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
