"""
Command Base Classes.

PATTERN: Command Pattern + CQRS
WHY:
  - Separates read/write concerns
  - Commands encapsulate write operations
  - Single responsibility
  - Easy to add cross-cutting concerns (logging, validation)

DECISION: Commands are classes with execute() method
WHY:
  - Can hold dependencies
  - Can be validated before execution
  - Can be logged/audited
  - Can be queued for async execution
"""

from abc import ABC, abstractmethod
from typing import Generic, TypeVar, Any
from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

# Type variable for command result
TResult = TypeVar("TResult")


class Command(ABC, Generic[TResult]):
    """
    Base class for all commands.
    
    Commands represent intentions to change state.
    They are write operations.
    
    USAGE:
        class CreateOrderCommand(Command[OrderCreateResponse]):
            def __init__(self, data: OrderCreate, session: AsyncSession):
                self.data = data
                self.session = session
            
            async def execute(self) -> OrderCreateResponse:
                # Implementation
    """
    
    @abstractmethod
    async def execute(self) -> TResult:
        """Execute the command and return result."""
        pass


class CommandHandler(ABC, Generic[TResult]):
    """
    Alternative pattern: Separate handler from command data.
    
    PATTERN: Command + Handler separation
    WHY:
      - Command is just data
      - Handler contains logic
      - Easier to test
      - Can have multiple handlers per command (decorators)
    
    We use Command with execute() for simplicity, but this is
    the more "pure" CQRS approach.
    """
    
    @abstractmethod
    async def handle(self, command: Any) -> TResult:
        """Handle the command."""
        pass


@dataclass
class CommandResult(Generic[TResult]):
    """
    Wrapper for command execution result.
    
    DECISION: Explicit success/failure wrapper
    WHY:
      - Clear success/failure indication
      - Can carry error details
      - Consistent return type
    """
    success: bool
    data: TResult | None = None
    error: str | None = None
    error_code: str | None = None
    
    @classmethod
    def ok(cls, data: TResult) -> "CommandResult[TResult]":
        """Create success result."""
        return cls(success=True, data=data)
    
    @classmethod
    def fail(cls, error: str, error_code: str = "ERROR") -> "CommandResult[TResult]":
        """Create failure result."""
        return cls(success=False, error=error, error_code=error_code)