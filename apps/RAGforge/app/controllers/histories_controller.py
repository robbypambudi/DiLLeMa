from src.services.rag.memorystore_service import MemorystoreService


class HistoriesController():

    def __init__(self, memorystore_service: MemorystoreService):
        """
        Controller for histories
        """
        self.memorystore_service = memorystore_service

    def get_all(self):
        """
        Get all histories
        """
        try:
            histories = self.memorystore_service.get_all_histories()
            return {
                "status": "success",
                "data": histories
            }
        except Exception as e:
            return {
                "status": "error",
                "message": str(e)
            }

    def get_memory_by_id(self, chat_id: str):
        """
        Get memory by chat id
        """
        try:
            memory = self.memorystore_service.get_memory(chat_id)
            return {
                "status": "success",
                "data": memory
            }
        except Exception as e:
            return {
                "status": "error",
                "message": str(e)
            }
