<center>
<h1>
Optimizing Chatbot System Performance Based on a Distributed Architecture using Multi-GPU Technology and The Ray Framework
</h1>

<strong>Implementation Guide</strong>

by:  
Ary Mazharuddin Shiddiqi, S. Kom, M.Comp.Sc, Ph.D.  
Robby Ulung Pambudi

SURABAYA, 2025


</center>

## Description
This research develops a chatbot system based on a distributed architecture using multi-GPU technology and the Ray framework. The system integrates Ray as a task distribution orchestrator framework, VLLM as an inference engine for large language models, Sentence Transformers-based text embedding for semantic processing, and Qdrant as a vector database. Ray acts as the main coordinator that manages workload distribution seamlessly. Testing was conducted on three models with different parameter sizes (0.5B, 1.5B, and 3B parameters) using three configurations: Single GPU, Multi-GPU, and Multi-GPU Multi-Node. The results show that the multi-GPU-based distributed system architecture successfully improves chatbot system performance with a throughput increase of up to 15-20% on the multi-node multi-GPU configuration compared to single GPU. The Multi-GPU configuration showed optimal performance in GPU utilization, achieving the highest utilization of 30% on the 3B parameter model and successfully optimizing GPU memory usage from 18 GB to approximately 13 GB per GPU through workload distribution. The Multi-GPU Multi-Node configuration showed the most efficient GPU utilization with a value of 4-10% for all model sizes, consistent CPU utilization of 77-78%, and successfully optimized system RAM usage to 8-9 GB. This research proves the effectiveness of distributed system architecture in optimizing parallel processing for various types of chatbot workloads.

## Benefits
The benefits of this implementation include:
1.  Providing implementation guidelines for system developers in building scalable chatbots that are capable of handling information requests in parallel with resource efficiency.
2.  Encouraging the use of open-source technologies such as Ray, vLLM, and Qdrant to build modern information systems that can be adapted in various sectors such as education, government, and other public services.
3.  Contributing to the development of knowledge in the fields of artificial intelligence and distributed systems, particularly related to the integration of Ray, vLLM, text embedding, and Qdrant technologies in chatbot development.

## Design
The architecture of this system is designed with reference to four main stages in the chatbot processing flow, namely the indexing stage, the context retrieval stage, the text generation stage, and the distributed system design.

### 1. Indexing
The indexing process begins by loading documents that will be used as knowledge sources into the system. Once the documents have been successfully loaded, a cleaning stage is carried out to remove irrelevant elements, such as special characters, excessive whitespace, or inconsistent formats. The cleaned documents are then processed by the document chunker module, which is tasked with dividing the documents into smaller chunks that are easier to process. After the chunking process is complete, each document fragment will go through a text embedding stage, which is the process of transforming text into a numerical vector representation. This vector representation is then stored in the Qdrant vector database, which serves as the main storage to support the context search process when the chatbot provides answers. A complete overview of the above process can be seen in Figure 3.1.

![Figure_3.1](/docs/assets/document_indexing.png)
Figure 3.1 Document indexing flowchart

The process of loading documents into the system is done using the `Pdfreader` library, which is part of the `pypdf` module, a Python library commonly used to read and process PDF files. This library enables the system to efficiently extract text content from pages in PDF documents, which can then be used as a data source for subsequent processing stages, such as cleaning, chunking, and vector representation (embedding) creation.

![Figure_3.2](/docs/assets/document_cleaning.png)
Figure 3.2 Document cleaning flowchart

Figure 3.2 shows the document cleaning process involving various types of tools from the natural language processing library, such as Punkt for sentence segmentation, stopwords to remove common words that have no significant meaning, WordNet as a basis for lexicalization, and Averaged Perceptron Tagger for part-of-speech tagging. In addition, the cleaning process also includes the stages of lemmatization, which is converting words to their basic form, and tokenization, which is breaking down text into units of words or tokens. These stages aim to simplify and standardize the content of the document so that it is more ready for processing in the next stage, such as chunking and embedding.

After the document goes through the cleaning stage, where the text content is filtered and simplified to remove irrelevant elements, the next process is the document chunking stage. At this stage, the cleaned document will be broken down into smaller pieces of text so that it can be processed more efficiently by machine learning models or text generation models that have a certain input length limit. This chunking process is carried out using libraries from the LangChain framework, specifically using two main components, `RecursiveCharacterTextSplitter` and `SentenceTransformersTokenTextSplitter`. `RecursiveCharacterTextSplitter` is used to split text based on character structure, taking into account various separators such as paragraphs, lines, periods, and spaces. This splitting strategy is recursive and flexible, allowing text to be divided in a way that maintains semantic coherence between sentences or paragraphs. Meanwhile, `SentenceTransformersTokenTextSplitter` plays a role in splitting based on the number of tokens, which is more suitable for ensuring that each chunk does not exceed the maximum token limit that can be accepted by transformer-based embedding models, such as Sentence Transformers. The combination of these two methods allows the chunking process to be carried out with high precision, maintaining a balance between the size of the text pieces and the quality of the information contained therein.

Furthermore, in the text embedding process, this study uses the Hugging Face Transformers library to obtain a model capable of converting text into high-dimensional numerical vector representations. The model used comes from a family of pre-trained models provided by Hugging Face, such as sentence-transformers, which have been optimized for semantic mapping, information retrieval, and text classification tasks. Using this model, each text chunk generated from the previous stage will be converted into an embedding vector that represents the content and meaning of the text in vector space. These vectors are then stored in a vector database, namely Qdrant, which will be used in the context retrieval stage in the chatbot system.

To speed up the indexing process for each document, it is run in the background so that it does not interfere with the main processes in the system. During this process, the system automatically records the status of each indexing stage, including information about the document being processed, the start and end times, and the success or failure status of the process.

### 2. Context Retrieval
Context retrieval is the process of searching for and retrieving relevant chunks based on statements given in the Vectorstore database. These relevant chunks are called contexts. The flowchart of the context retrieval process can be seen in Figure 3.3.

![Figure_3.3](/docs/assets/context_retrieval.png)
Figure 3.3 Context retrieval system

There are several ways to obtain context using a vector store. Figure 3.3 shows a context retrieval system commonly used in RAG development, but this system has a weakness: the quality of the relevant documents obtained is highly dependent on the initial query. Therefore, the AI Agent approach is used to generate more accurate answers. With Al Agent, the initial question is "augmented" or enriched before being resubmitted to the vector store. After that, the search results need to be re-ranked, and the highest-ranked documents are selected as context to ensure the accuracy of the answers. The flowchart of context retrieval using Al agents can be seen in Figure 3.4.

![Figure_3.4](/docs/assets/agentic_ai.png)
Figure 3.4 Context retrieval system using agentic AI

By implementing this system, the context retrieval process can run with a higher level of accuracy. This is achieved through the augmentation of questions by Al agents before they are sent to the vector store, as well as the application of a re-ranking mechanism to select the most relevant documents to be used as context, so that the information presented is more accurate and relevant to the needs.

### 3. Text Generation
In this system, text generation uses an approach related to Natural Language Processing (NLP). The goal is to produce text or responses that resemble human language. This process involves text generation models, such as Large Language Models (LLMs) or generative AI. The flow of the text generation process can be seen in Figure 3.5.

![Figure_3.5](/docs/assets/text_generation.png)
Figure 3.5 Text generation system

Text generation is commonly used in chatbot applications and various other applications that require natural language interaction with users. In the initial stage, the system will use the results of the indexing process in the form of relevant document snippets. These relevant document snippets (context) are then processed to be used as reference answers for each question asked to the chatbot. In this case, the text generation model also acts as a verifier that determines whether the given context is relevant to the question asked. If the model cannot find the right answer, the response given is "Sorry, I don't have enough information to answer this question." The model's ability to generate the right answer is regulated through prompts, which are provided by the LangChain library, specifically through the `SystemMessage` module. These prompts serve to direct the model in generating text that is appropriate to the context that has been found.

### 4. Distributed LLM Design
The design of a distributed LLM system involves two main frameworks, namely Ray and VLLM. Ray acts as a distributed resource management and orchestration framework; with features such as automatic task scheduling, autoscaling, and fault tolerance, Ray allows model inference and training workloads to be dynamically allocated to various nodes. 

![Figure_3.6](/docs/assets/distributed_llm_system.png)
Figure 3.6 Distributed LLM system architecture

Meanwhile, vLLM focuses on optimizing LLM inference performance through techniques such as dynamic batching, kernel fusion, and advanced memory management, which significantly increase throughput and reduce latency. The integration of Ray with VLLM combines large-scale orchestration with efficient inference execution, enabling the system to not only serve large-scale parallel requests but also maintain responsiveness and optimal GPU utilization. Thus, the collaboration between these two frameworks forms a solid foundation for reliable and high-performance distributed LLM implementations.

## Implementation
This system is categorized into three main parts: first, the backend system that handles data and document management; second, the frontend system that handles user input through a web interface; and third, the Large Language Model (LLM)-based processing system that understands questions and generates relevant answers.

### 1. Backend Implementation Results
The backend of this system was developed using the FastAPI framework, which is known for being lightweight, fast, and easy to integrate with automatic documentation using Swagger UI. The backend is responsible for data management, user request processing, and interaction with the RAG (Retrieval-Augmented Generation) model. Some of the main endpoints that have been implemented include the following:

**Table 4.1 List of RAG backend endpoints**

| No | Api | Metode | Keterangan |
| --- | --- | --- | --- |
| 1 | /api/v1/collection | GET | Used to display a list of available document collections |
| 2 | /api/v1/collection | POST | Used to create a new collection. |
| 3 | /api/v1/collection/{collection\_name} | GET | Retrieve collection information based on collection name. |
| 4 | /api/v1/collection/{collection name} | DELETE | Delete a specific collection. |
| 5 | /api/v1/files | GET | Display all uploaded document files. |
| 6 | /api/v1/files | POST | Uploads document files to the system. |
| 7 | /api/v1/files/{file\_id} | GET | Retrieves files based on their ID. |
| 8 | /api/v1/files/{file\_id} | DELETE | Deletes files based on their ID. |
| 9 | /api/v1/questions | POST | Sends questions to the system and receives document-based answers. |
| 10 | /api/v1/questions/stream | POST | Same as previous endpoint, but provides streaming responses for a more interactive user experience. |
| 11 | /api/v1/questions/clear-all | POST | Deletes the entire history of questions and answers in the user session. |

These endpoints are grouped according to their function (collection, files, questions), which demonstrates modularity in the backend design. The Swagger UI documentation shown in Figure 4.1 indicates that this system has fulfilled the aspects of good API documentation, with a clear and descriptive endpoint structure. 

![Figure_4.1](/docs/assets/be_documentation.png)
Figure 4.1 Backend documentation within Swagger UI

With a modular endpoint structure that is well documented through Swagger UI, this backend implementation supports the entire system workflow, from collection and file management to RAG model-based question-and-answer processes.

### 2. Frontend Implementation Results
On the landing page, users are greeted with a brief welcome message, a button to start chatting that leads to the chatbot's main page, and a button to toggle the display theme from light mode to dark mode.

![Figure_4.2](/docs/assets/light_mode_landing.png)
Figure 4.2 Light mode display of chatbot landing page

![Figure_4.3](/docs/assets/dark_mode_landing.png)
Figure 4.3 Darkmode display of chatbot landing page

On the main page, users are greeted with a sidebar containing a selection of document collections that will be used as the chatbot's knowledge base. After selecting a collection, the sidebar will highlight the active collection along with a brief description, followed by the opening of the main display and chat window at the bottom. Users can type questions in the input field at the bottom of the page and press the send icon to start a question-and-answer session. All messages sent and received will be displayed sequentially in the chat window, providing an interaction experience similar to instant messaging applications.

![Figure_4.4](/docs/assets/main.png)
Figure 4.4 Chatbot main page display

![Figure_4.5](/docs/assets/collection.png)
Figure 4.5 shows the chatbot system display after the user selects one of the document collections, namely the collection named "Computer Networks - Module 1". 

In the middle of the page, the system will answer questions from users according to the active collection. In this example, the chatbot provides information on how to crimp an RJ-45 UTP LAN cable, which includes several important points, such as:
* Required materials.
* Cable configuration, straight-over or crossover.
* Steps to follow.

![Figure_4.6](/docs/assets/export.png)
Figure 4.6 shows the results of downloading chat history with the chatbot system in HTML format

For each answer provided by the system, there are two hidden buttons that will appear when the user places the cursor over the area: a copy answer button and a download conversation button. The copy button will copy the answer highlighted by the user to the clipboard, while the download conversation button will generate an HTML file that will save the chat history with the system.

This display shows how the system can function as a document-based interactive assistant, where the contents of the collection are used as a source of knowledge that can be referenced when users ask questions. At the bottom of the page, there is a question input field that allows users to type and submit questions related to the document being displayed. After the user submits a question, the system will display the response directly in the form of a sequential conversation.

### 3. Distributed Large Language Model Implementation Results
To support efficient LLM model inference and management processes, this system is implemented in a distributed manner using the Ray framework. Ray enables parallel workload execution and more optimal management of computing resources such as CPU, memory, and disk in a cluster. The single-GPU Ray Dashboard is shown in Figure 4.7, which displays the status of active nodes in the cluster. In this configuration, the system runs on one main node (head node) with the IP address 10.21.73.122. The node is active (ALIVE) and is tasked with running the main LLM service process. 

![Figure_4.7](/docs/assets/single_gpu.png)
Figure 4.7 Ray dashboard display for single-GPU

The information displayed includes CPU usage (13%), memory allocation (10.6 GiB out of 52.5 GiB), and disk and GRAM status showing storage and processing capacity. In addition, bandwidth usage and process log status information is also available, facilitating real-time system performance monitoring.

![Figure_4.8](/docs/assets/single_node_multi_gpu.png)
Figure 4.8 Ray dashboard display for single-Node multi-GPU

The multi-GPU configuration on a single node is shown in Figure 4.8. In this display, there are two active nodes: the first node functions as the head, while the second node acts as the worker. In the GPU column, it can be seen that each node has two active GPUs.

![Figure_4.9](/docs/assets/multi_node_multi_gpu.png)
Figure 4.9 Ray dashboard display for multi-Node multi-GPU

Meanwhile, in a multi-GPU and multi-Node configuration, each Node is equipped with one GPU, as shown in Figure 4.9.