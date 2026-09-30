from google import genai
from google.genai import types
from typing import List, Optional, Dict, Any

class AIGenerator:
    """Handles interactions with Google's Gemini API for generating responses"""
    
    # Static system prompt to avoid rebuilding on each call
    SYSTEM_PROMPT = """ You are an AI assistant specialized in course materials and educational content with access to a comprehensive search tool for course information.

Search Tool Usage:
- Use the search tool **only** for questions about specific course content or detailed educational materials
- **One search per query maximum**
- Synthesize search results into accurate, fact-based responses
- If search yields no results, state this clearly without offering alternatives

Response Protocol:
- **General knowledge questions**: Answer using existing knowledge without searching
- **Course-specific questions**: Search first, then answer
- **No meta-commentary**:
 - Provide direct answers only — no reasoning process, search explanations, or question-type analysis
 - Do not mention "based on the search results"


All responses must be:
1. **Brief, Concise and focused** - Get to the point quickly
2. **Educational** - Maintain instructional value
3. **Clear** - Use accessible language
4. **Example-supported** - Include relevant examples when they aid understanding
Provide only the direct answer to what was asked.
"""
    
    def __init__(self, api_key: str, model: str):
        self.client = genai.Client(api_key=api_key)
        self.model = model

    def _config(self, system_content: str, tools: Optional[List] = None) -> types.GenerateContentConfig:
        """Build generation config; tool calls are executed manually, not automatically."""
        kwargs: Dict[str, Any] = {
            "system_instruction": system_content,
            "temperature": 0,
            "max_output_tokens": 800,
            "thinking_config": types.ThinkingConfig(thinking_budget=0),
        }
        if tools:
            kwargs["tools"] = [types.Tool(function_declarations=[
                types.FunctionDeclaration(
                    name=t["name"],
                    description=t["description"],
                    parameters_json_schema=t["input_schema"],
                )
                for t in tools
            ])]
            kwargs["automatic_function_calling"] = types.AutomaticFunctionCallingConfig(disable=True)
        return types.GenerateContentConfig(**kwargs)

    def generate_response(self, query: str,
                         conversation_history: Optional[str] = None,
                         tools: Optional[List] = None,
                         tool_manager=None) -> str:
        """
        Generate AI response with optional tool usage and conversation context.

        Args:
            query: The user's question or request
            conversation_history: Previous messages for context
            tools: Available tools the AI can use (name/description/input_schema dicts)
            tool_manager: Manager to execute tools

        Returns:
            Generated response as string
        """
        system_content = (
            f"{self.SYSTEM_PROMPT}\n\nPrevious conversation:\n{conversation_history}"
            if conversation_history
            else self.SYSTEM_PROMPT
        )

        contents = [types.Content(role="user", parts=[types.Part(text=query)])]
        response = self.client.models.generate_content(
            model=self.model,
            contents=contents,
            config=self._config(system_content, tools),
        )

        if response.function_calls and tool_manager:
            return self._handle_tool_execution(response, contents, system_content, tool_manager)

        return response.text or ""

    def _handle_tool_execution(self, initial_response, contents: List, system_content: str, tool_manager) -> str:
        """Execute requested tool calls, then make a follow-up call without tools."""
        contents = contents + [initial_response.candidates[0].content]

        result_parts = []
        for call in initial_response.function_calls:
            tool_result = tool_manager.execute_tool(call.name, **(call.args or {}))
            result_parts.append(types.Part.from_function_response(
                name=call.name,
                response={"result": tool_result},
            ))
        contents.append(types.Content(role="user", parts=result_parts))

        final_response = self.client.models.generate_content(
            model=self.model,
            contents=contents,
            config=self._config(system_content),
        )
        return final_response.text or ""
