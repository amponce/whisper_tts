import os
import io
import time
import tempfile
from openai import OpenAI
import speech_recognition as sr
from pydub import AudioSegment
from pydub.playback import play
from config import *
import interpreter

# Initialize OpenAI client
client = OpenAI(api_key=OPENAI_API_KEY)
assistant_id = None
thread_id = None

# Initialize Open Interpreter
interpreter.api_key = OPENAI_API_KEY
interpreter.model = OPENAI_MODEL
interpreter.auto_run = INTERPRETER_AUTO_RUN

def get_or_create_thread():
    global thread_id
    if thread_id:
        try:
            client.beta.threads.retrieve(thread_id)
            return thread_id
        except Exception as e:
            print(f"Error retrieving thread: {e}")
    
    try:
        thread = client.beta.threads.create()
        thread_id = thread.id
        print(f"New thread created with ID: {thread_id}")
        return thread_id
    except Exception as e:
        print(f"Error creating thread: {e}")
        return None

def initialize_assistant():
    global assistant_id
    if ASSISTANT_ID:
        try:
            assistant = client.beta.assistants.retrieve(ASSISTANT_ID)
            print(f"Using existing assistant with ID: {assistant.id}")
            assistant_id = assistant.id
            return assistant_id
        except Exception as e:
            print(f"Error retrieving assistant: {e}")
    
    try:
        assistant = client.beta.assistants.create(
            name="Athena",
            instructions=ATHENA_INSTRUCTIONS,
            model=OPENAI_MODEL,
            tools=ATHENA_TOOLS
        )
        print(f"New assistant created with ID: {assistant.id}")
        assistant_id = assistant.id
        return assistant_id
    except Exception as e:
        print(f"Error creating assistant: {e}")
        return None

def analyze_audio(user_prompt):
    if not client.api_key or not assistant_id:
        return "OpenAI functionalities are disabled or assistant is not initialized. Cannot analyze audio."

    try:
        thread_id = get_or_create_thread()
        if not thread_id:
            return "Failed to create or retrieve a thread. Cannot process the request."

        client.beta.threads.messages.create(
            thread_id=thread_id,
            role="user",
            content=user_prompt
        )

        run = client.beta.threads.runs.create(
            thread_id=thread_id,
            assistant_id=assistant_id,
            instructions=f"""Remember to address the user as {USER_NAME} and maintain your friendly, supportive demeanor.
            If the user wants to start an Open Interpreter session, inform them to say 'Start Open Interpreter'."""
        )

        while True:
            run_status = client.beta.threads.runs.retrieve(thread_id=thread_id, run_id=run.id)
            if run_status.status == 'completed':
                break
            elif run_status.status in ['failed', 'cancelled', 'expired']:
                return f"Run failed with status: {run_status.status}"
            time.sleep(1)

        messages = client.beta.threads.messages.list(
            thread_id=thread_id,
            order="desc",
            limit=1
        )

        if messages.data:
            latest_message = messages.data[0]
            if latest_message.role == "assistant":
                return latest_message.content[0].text.value
        
        return f"I'm sorry, {USER_NAME}, I didn't receive a response. How else can I assist you?"

    except Exception as e:
        print(f"Error in analyze_audio: {e}")
        return f"I'm sorry, {USER_NAME}, I encountered an error while processing your request. How can I help you differently?"

def open_interpreter_session():
    print(f"Starting Open Interpreter session. Say 'Exit Interpreter' to end the session.")
    play_audio("Entering Open Interpreter mode. Say 'Exit Interpreter' to end the session.", voice="onyx")

    while True:
        user_input = get_audio_input()
        if user_input is None:
            print("No input detected. Waiting for your command in Open Interpreter mode.")
            continue
        if user_input.lower() == "exit interpreter":
            play_audio("Exiting Open Interpreter mode.", voice="onyx")
            return "Open Interpreter session ended."

        try:
            response = interpreter.chat(user_input)
            print("Open Interpreter:", response)
            play_audio(response, voice="onyx")  # Using a different voice for Open Interpreter
        except Exception as e:
            error_message = f"Error in Open Interpreter: {str(e)}"
            print(error_message)
            play_audio(error_message, voice="onyx")

def play_audio(text, voice="nova"):
    try:
        if client is None:
            print("OpenAI client not initialized. Skipping text-to-speech.")
            return
        if not isinstance(text, str):
            text = str(text)

        response = client.audio.speech.create(
            model="tts-1",
            voice=voice,
            input=text,
        )

        audio = AudioSegment.from_file(io.BytesIO(response.content), format="mp3")
        play(audio)
    except Exception as e:
        print(f"Error in play_audio: {e}")

def get_audio_input():
    recognizer = sr.Recognizer()
    with sr.Microphone() as source:
        print("Listening for speech...")
        recognizer.adjust_for_ambient_noise(source, duration=0.5)
        try:
            audio = recognizer.listen(
                source,
                timeout=SPEECH_RECOGNITION_TIMEOUT,  # Consider increasing this value
                phrase_time_limit=SPEECH_RECOGNITION_PHRASE_TIME_LIMIT  # And this one
            )
            print("Processing...")
        except sr.WaitTimeoutError:
            print("No speech detected within the timeout period.")
            return None

    try:
        transcript = transcribe_audio(audio)
        if transcript:
            print(f"Transcribed audio: {transcript}")
            return transcript
        else:
            print("No speech detected or transcription failed.")
            return None
    except sr.UnknownValueError:
        print("Speech recognition could not understand the audio.")
        return None
    except sr.RequestError as e:
        print(f"Could not request results from speech recognition service; {e}")
        return None

def transcribe_audio(audio):
    if client is None:
        print("OpenAI client not initialized. Skipping transcription.")
        return None
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=".wav") as temp_audio:
            temp_audio.write(audio.get_wav_data())
            temp_audio_path = temp_audio.name

        with open(temp_audio_path, "rb") as audio_file:
            start_time = time.time()
            transcript = client.audio.transcriptions.create(
                model="whisper-1",
                file=audio_file,
                response_format="text"
            ).strip()
            print(f"Time to transcribe audio: {time.time() - start_time:.2f} seconds")

        os.unlink(temp_audio_path)
        return transcript
    except Exception as e:
        print(f"Error in transcribe_audio: {e}")
        return None

def main():
    global assistant_id
    print(f"Initializing Athena, {USER_NAME}'s personal AI companion...")
    print(f"Using model: {OPENAI_MODEL}")
    assistant_id = initialize_assistant()
    if not assistant_id:
        print("Failed to initialize assistant. Exiting.")
        return

    # Add the welcome message here
    welcome_message = f"Hey {USER_NAME}! What's up!"
    print(f"Athena: {welcome_message}")
    play_audio(welcome_message)

    print("Listening for speech...")
    while True:
        try:
            user_prompt = get_audio_input()
            if user_prompt is None:
                print("No input detected. Waiting for your command.")
                continue
            if user_prompt.lower() in ["exit", "quit", "goodbye"]:
                print(f"Athena: Goodbye, {USER_NAME}! Have a great day.")
                play_audio(f"Goodbye, {USER_NAME}! Have a great day.")
                break

            print(f"{USER_NAME}:", user_prompt)

            if user_prompt.lower() == "start open interpreter":
                response = open_interpreter_session()
                print("Athena:", response)
                play_audio(response)
            else:
                analysis = analyze_audio(user_prompt)
                print("Athena:", analysis)
                play_audio(analysis)

            time.sleep(1)  # Small delay after playing audio
        except KeyboardInterrupt:
            print(f"\nThank you for chatting with Athena. Goodbye, {USER_NAME}!")
            play_audio(f"Thank you for chatting with me. Goodbye, {USER_NAME}!")
            break
        except Exception as e:
            print(f"An error occurred: {e}. Athena is ready to assist with something else.")
            play_audio(f"An error occurred: {e}. I'm ready to assist with something else.")

        print("Listening for speech...")

if __name__ == "__main__":
    main()