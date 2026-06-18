# agents.py
from langchain_ollama import ChatOllama
from langchain_core.prompts import ChatPromptTemplate
from state import SoftwareState, ModuleList, ArchitectureDoc, CodeReview
import json
from dotenv import load_dotenv
load_dotenv()

# Configuration
BASE_URL = "https://ollama.com" 
MODEL_NAME = "gemma4:31b-cloud" 

llm = ChatOllama(base_url=BASE_URL, model=MODEL_NAME, temperature=0)

# --- Nodes ---

def planner_node(state: SoftwareState):
    print("--- 📝 PLANNER: Analyzing Requirements ---")
    
    prompt = ChatPromptTemplate.from_template(
        "Analyze the following requirement and generate user stories and a list of backend modules.\n"
        "Requirement: {requirement}\n"
        "Respond with a JSON object containing 'stories' (list of strings) and 'modules' (list of strings). "
        "Modules should be simple names like 'auth', 'users', 'inventory'."
    )
    
    chain = prompt | llm
    response = chain.invoke({"requirement": state["requirement"]})
    
    try:
        content = response.content
        # Clean up markdown if present
        if "```json" in content:
            content = content.split("```json")[1].split("```")[0]
        
        data = json.loads(content)
        
        # --- SANITIZATION LOGIC ---
        # Ensure modules are strictly strings, not dictionaries
        raw_modules = data.get("modules", [])
        clean_modules = []
        
        for m in raw_modules:
            if isinstance(m, str):
                clean_modules.append(m)
            elif isinstance(m, dict):
                # If LLM returns objects, extract the 'name' key
                clean_modules.append(m.get('name', str(m)))
            else:
                clean_modules.append(str(m))
        # ---------------------------

        return {
            "stories": data.get("stories", []),
            "modules": clean_modules,
            "pending_modules": clean_modules,
            "completed_modules": []
        }
    except Exception as e:
        print(f"Error parsing Planner output: {e}")
        # Fallback
        return {
            "stories": ["Create basic system"],
            "modules": ["main"],
            "pending_modules": ["main"],
            "completed_modules": []
        }

def architect_node(state: SoftwareState):
    print("--- 🏗️  ARCHITECT: Designing System ---")
    
    prompt = ChatPromptTemplate.from_template(
        "You are a Software Architect. Design a system for these stories: {stories}.\n"
        "Modules involved: {modules}.\n"
        "Provide Database Schema, API Design, and Folder Structure. Use FastAPI."
    )
    
    chain = prompt | llm
    response = chain.invoke({
        "stories": state["stories"], 
        "modules": state["modules"]
    })
    
    return {"architecture": response.content}

def backend_lead_node(state: SoftwareState):
    """
    Dispatcher logic.
    """
    print("--- 👷 BACKEND LEAD: Assigning Work ---")
    
    pending = state["pending_modules"]
    
    if not pending:
        print("All modules completed.")
        return {"current_module": None}
    
    # Get the next module
    next_module = pending[0]
    
    # --- SAFETY CHECK ---
    # Convert dict to string if sanitization failed earlier
    if isinstance(next_module, dict):
        next_module = next_module.get('name', str(next_module))
    # -------------------

    # Update lists
    new_pending = pending[1:]
    
    print(f"Assigning module: {next_module}")
    
    return {
        "current_module": next_module,
        "pending_modules": new_pending
    }

def module_agent_node(state: SoftwareState):
    print(f"--- 💻 MODULE AGENT: Coding {state['current_module']} ---")
    
    module = state["current_module"]
    arch = state["architecture"]
    
    prompt = ChatPromptTemplate.from_template(
        "You are an expert Python Backend Developer.\n"
        "Generate complete, production-ready FastAPI code for the module: '{module}'.\n"
        "Context:\n{architecture}\n\n"
        "Return ONLY the Python code inside a markdown code block."
    )
    
    chain = prompt | llm
    response = chain.invoke({"architecture": arch, "module": module})
    
    code = response.content
    
    # Update generated_code dict
    # module is now guaranteed to be a string (hashable)
    current_code_map = state.get("generated_code", {})
    current_code_map[module] = code
    
    return {
        "generated_code": current_code_map,
        "fix_attempts": 0 
    }

def reviewer_node(state: SoftwareState):
    print("--- 🔍 REVIEWER: Checking Code ---")
    
    module = state["current_module"]
    code = state["generated_code"].get(module, "")
    
    prompt = ChatPromptTemplate.from_template(
        "Review the following code for the module '{module}'.\n"
        "Code:\n{code}\n\n"
        "Provide a JSON response with keys: 'score' (int 1-10), 'issues' (list of strings)."
    )
    
    chain = prompt | llm
    response = chain.invoke({"code": code, "module": module})
    
    try:
        content = response.content
        if "```json" in content:
            content = content.split("```json")[1].split("```")[0]
        data = json.loads(content)
    except:
        data = {"score": 5, "issues": ["Parsing failed"]}
        
    return {
        "review_score": data.get("score", 5),
        "review_issues": data.get("issues", [])
    }

def fixer_node(state: SoftwareState):
    print("--- 🛠️  FIXER: Applying Corrections ---")
    
    module = state["current_module"]
    code = state["generated_code"].get(module, "")
    issues = state["review_issues"]
    
    prompt = ChatPromptTemplate.from_template(
        "Fix the following code based on the issues provided.\n"
        "Module: {module}\n"
        "Current Code:\n{code}\n\n"
        "Issues:\n{issues}\n\n"
        "Return ONLY the corrected Python code."
    )
    
    chain = prompt | llm
    response = chain.invoke({
        "module": module,
        "code": code,
        "issues": "\n".join(issues)
    })
    
    fixed_code = response.content
    current_code_map = state["generated_code"]
    current_code_map[module] = fixed_code
    
    return {
        "generated_code": current_code_map
    }