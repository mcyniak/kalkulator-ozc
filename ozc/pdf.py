"""Wspólna blokada dla biblioteki PDFium — nie jest bezpieczna wielowątkowo (Streamlit + równoległe odczyty)."""
import threading

BLOKADA_PDF = threading.RLock()
