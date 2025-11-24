"""
Prompt templates for LLM-based grading and explanation generation.
"""

def build_grading_prompt(
    taxonomy_context: str,
    question_title: str,
    question_description: str,
    parts_content: str,
    options_content: str,
    correct_answer_text: str,
    user_answer_text: str,
    is_single_correct: bool,
) -> str:
    """
    Build a prompt for grading a user's answer with LLM.
    
    Args:
        taxonomy_context: Full taxonomical hierarchy context
        question_title: The question title
        question_description: Question description or additional context
        parts_content: Formatted question parts (text, images, etc.)
        options_content: Formatted answer options
        correct_answer_text: The correct answer(s)
        user_answer_text: The user's submitted answer
        is_single_correct: Whether this is a single-correct answer question
    
    Returns:
        Formatted prompt string for LLM
    """
    scoring_instruction = (
        "CRITICAL: This is a single-correct question. Score MUST be exactly 0.0 (wrong) or 1.0 (correct). NO partial scores allowed."
        if is_single_correct
        else "Score can be partial (0.0 to 1.0) for multi-correct questions."
    )
    
    return f"""
You are an expert tutor. Grade the user's answer and provide a helpful explanation.

{taxonomy_context}
Question: {question_title}
{question_description}

{parts_content}

{options_content}

Correct Answer: {correct_answer_text}
User Answer: {user_answer_text}

Provide:
- Detailed explanation blocks covering what's correct, what's missing, and complete explanations.
- A score from 0.0 to 1.0 (determined AFTER generating explanation)

IMPORTANT INSTRUCTIONS:
1. {scoring_instruction}
2. Keep the explanation SWEET AND SHORT. Maximum 100-150 words total.
3. Use proper MARKDOWN formatting (bold, lists, etc.) to make it readable.
4. Ground your explanation with factual information from reliable sources using Google Search.
5. Consider the full taxonomical hierarchy context when scoring and explaining.
"""
