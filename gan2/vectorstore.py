import os
import faiss
import numpy as np
import pickle
from typing import List, Any
from sentence_transformers import SentenceTransformer
from gan2.embedding import EmbeddingPipeline

class FaissVectorStore:
    def __init__(self, persist_dir: str = "faiss_store", embedding_model: str = "all-MiniLM-L6-v2", chunk_size: int = 1000, chunk_overlap: int = 200):
        self.persist_dir = persist_dir
        os.makedirs(self.persist_dir, exist_ok=True)
        self.index = None
        self.metadata = []
        self.embedding_model = embedding_model
        self.model = SentenceTransformer(embedding_model)
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap
        print(f"[INFO] Loaded embedding model: {embedding_model}")

    def build_from_documents(self, documents: List[Any]):
        print(f"[INFO] Building vector store from {len(documents)} raw documents...")
        emb_pipe = EmbeddingPipeline(model_name=self.embedding_model, chunk_size=self.chunk_size, chunk_overlap=self.chunk_overlap)
        #  first get chunks from splitting uploaded docs -> return chunks -> documnets structure(texts,metadatas)
        chunks = emb_pipe.chunk_documents(documents)
        # Second get embeddings(the numpy array contain mathematical representation of splitted texts )
        embeddings = emb_pipe.embed_chunks(chunks)
        # As we dealing with document structure its easy to get the metadata from original chunks
        metadatas = [{"text": chunk.page_content} for chunk in chunks]
        self.add_embeddings(np.array(embeddings).astype('float32'), metadatas)
        self.save()
        print(f"[INFO] Vector store built and saved to {self.persist_dir}")

    def add_embeddings(self, embeddings: np.ndarray,  metadatas: List[Any] = None):
        dim = embeddings.shape[1]
        ids = np.arange(len(embeddings)).astype(np.int64)
        if self.index is None:
            faiss.normalize_L2(embeddings)
            self.index = faiss.IndexIDMap(faiss.IndexFlatIP(dim))
            self.index.add_with_ids(embeddings,ids)
            #self.index = faiss.IndexFlatL2(dim)
        #self.index.add(embeddings)
        if metadatas:
            self.metadata.extend(metadatas)
        print(f"[INFO] Added {embeddings.shape[0]} vectors to Faiss index.")

    def save(self):
        faiss_path = os.path.join(self.persist_dir, "faiss.index")
        meta_path = os.path.join(self.persist_dir, "metadata.pkl")
        # Save FAISS index to disk
        faiss.write_index(self.index, faiss_path)
        with open(meta_path, "wb") as f:
            pickle.dump(self.metadata, f)
        print(f"[INFO] Saved Faiss index and metadata to {self.persist_dir}")

    def load(self):
        faiss_path = os.path.join(self.persist_dir, "faiss.index")
        meta_path = os.path.join(self.persist_dir, "metadata.pkl")
        self.index = faiss.read_index(faiss_path)
        with open(meta_path, "rb") as f:
            self.metadata = pickle.load(f)
        print(f"[INFO] Loaded Faiss index and metadata from {self.persist_dir}")

    

    def search(self, query_embedding: np.ndarray, top_k: int = 3, min_score: float = 0.1):
        
        """
        Search the FAISS index for the query_embedding.
        
        Args:
            query_embedding: np.ndarray of shape (1, dim)
            top_k: number of top results to return
            min_score: minimum cosine similarity to consider a result relevant

        Returns:
            List of results or a message saying no relevant info found
        """
        D, I = self.index.search(query_embedding, top_k)

        results = []
        for idx, score in zip(I[0], D[0]):
            if score < min_score:  # Filter irrelevant results
                continue
            meta = self.metadata[idx] if idx < len(self.metadata) else None
            results.append({
                "id": int(idx),
                "score": float(score),
                "metadata": meta
            })

        if not results:
            return [{"message": "No relevant info found."}]

        return results



    def query(self, query_text: str, top_k: int = 5):
        print(f"[INFO] Querying vector store for: '{query_text}'")
        query_emb = self.model.encode([query_text]).astype('float32')
        faiss.normalize_L2(query_emb)
        return self.search(query_emb, top_k=top_k)
    
