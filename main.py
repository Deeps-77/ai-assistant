# main.py
from graph import app
from state import SoftwareState

# Initial State
initial_state: SoftwareState = {
    "requirement": "Build an Inventory Management System with Authentication and User Management.",
    "stories": [],
    "architecture": None,
    "modules": [],
    "pending_modules": [],
    "completed_modules": [],
    "current_module": None,
    "generated_code": {},
    "review_score": None,
    "review_issues": [],
    "fix_attempts": 0
}

if __name__ == "__main__":
    print("🚀 Starting AI Software Delivery Team...")
    
    # Run the graph
    # config={"recursion_limit": 100} prevents infinite loops in case of bugs
    result = app.invoke(initial_state, config={"recursion_limit": 100})
    
    print("\n\n=== 🎉 WORKFLOW COMPLETE ===")
    
    print("\n--- Generated Architecture ---")
    print(result["architecture"])
    
    print("\n--- Generated Modules ---")
    for module, code in result["generated_code"].items():
        print(f"\n[Module: {module}]")
        # Just print first 500 chars to verify
        print(code[:500] + "...") 