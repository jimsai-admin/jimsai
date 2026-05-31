"""
Event Store Implementation - Append-only log with projections

Uses PostgreSQL for durability and CQRS projections
for maintaining read-optimized views.
"""

import json
import logging
import asyncio
from datetime import datetime
from typing import Any, Dict, List, Optional, Callable
from uuid import UUID
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from .events import DomainEvent, EVENT_REGISTRY

logger = logging.getLogger(__name__)


class EventStore:
    """Append-only event log with subscription and projection support"""
    
    def __init__(self, db_session: AsyncSession):
        self.db = db_session
        self.subscriptions: Dict[str, List[Callable]] = {}
        self.projections: List[Any] = []
    
    async def append(self, event: DomainEvent) -> Dict[str, Any]:
        """
        Write event to append-only log
        
        Args:
            event: Domain event to persist
            
        Returns:
            Event record with ID and timestamp
        """
        
        # Serialize event
        event_dict = event.to_dict()
        event_type = event.__class__.__name__
        aggregate_id = str(event.aggregate_id)
        
        try:
            # Insert into events table
            result = await self.db.execute(
                text("""
                    INSERT INTO events (
                        event_type, aggregate_id, aggregate_type,
                        data, metadata, created_at, version
                    ) VALUES (
                        :event_type, :aggregate_id, :aggregate_type,
                        :data, :metadata, NOW(), :version
                    )
                    RETURNING id, created_at, event_type
                """),
                {
                    "event_type": event_type,
                    "aggregate_id": aggregate_id,
                    "aggregate_type": event.aggregate_type,
                    "data": json.dumps(event_dict),
                    "metadata": json.dumps({
                        "timestamp": event.timestamp.isoformat() if event.timestamp else None,
                        "version": event.version,
                    }),
                    "version": event.version,
                }
            )
            
            await self.db.commit()
            row = result.fetchone()
            
            logger.info(f"Event appended: {event_type} (ID: {row[0]})")
            
            # Trigger subscriptions asynchronously
            await self._trigger_subscriptions(event)
            
            # Process projections
            await self._process_projections(event)
            
            return {
                "id": row[0],
                "created_at": row[1],
                "event_type": row[2],
                "aggregate_id": aggregate_id,
            }
            
        except Exception as e:
            await self.db.rollback()
            logger.error(f"Failed to append event {event_type}: {str(e)}")
            raise
    
    async def get_aggregate_events(
        self, 
        aggregate_id: str,
        from_version: int = 0
    ) -> List[DomainEvent]:
        """
        Get all events for an aggregate, in order
        
        Args:
            aggregate_id: ID of aggregate
            from_version: Start from this version
            
        Returns:
            List of domain events in chronological order
        """
        
        result = await self.db.execute(
            text("""
                SELECT event_type, data, metadata, version, created_at
                FROM events
                WHERE aggregate_id = :aggregate_id AND version >= :from_version
                ORDER BY created_at ASC, version ASC
            """),
            {
                "aggregate_id": str(aggregate_id),
                "from_version": from_version,
            }
        )
        
        rows = result.fetchall()
        events = []
        
        for row in rows:
            event_type = row[0]
            data = json.loads(row[1])
            
            # Reconstruct event from data
            if event_type in EVENT_REGISTRY:
                event_class = EVENT_REGISTRY[event_type]
                event = event_class(**data)
                events.append(event)
        
        return events
    
    async def get_events_by_type(
        self, 
        event_type: str,
        limit: int = 100,
        offset: int = 0
    ) -> List[DomainEvent]:
        """Get recent events of a specific type"""
        
        result = await self.db.execute(
            text("""
                SELECT event_type, data, metadata, created_at
                FROM events
                WHERE event_type = :event_type
                ORDER BY created_at DESC
                LIMIT :limit OFFSET :offset
            """),
            {
                "event_type": event_type,
                "limit": limit,
                "offset": offset,
            }
        )
        
        rows = result.fetchall()
        events = []
        
        for row in rows:
            event_type_name = row[0]
            data = json.loads(row[1])
            
            if event_type_name in EVENT_REGISTRY:
                event_class = EVENT_REGISTRY[event_type_name]
                event = event_class(**data)
                events.append(event)
        
        return events
    
    async def get_events_in_range(
        self,
        workspace_id: str,
        start_time: datetime,
        end_time: datetime,
        event_types: Optional[List[str]] = None
    ) -> List[DomainEvent]:
        """Get events in time range, optionally filtered by type"""
        
        query = """
            SELECT event_type, data, created_at
            FROM events
            WHERE created_at >= :start_time 
              AND created_at <= :end_time
        """
        
        params = {
            "start_time": start_time,
            "end_time": end_time,
        }
        
        if event_types:
            placeholders = ",".join([f"'{et}'" for et in event_types])
            query += f" AND event_type IN ({placeholders})"
        
        query += " ORDER BY created_at ASC"
        
        result = await self.db.execute(text(query), params)
        rows = result.fetchall()
        
        events = []
        for row in rows:
            event_type = row[0]
            data = json.loads(row[1])
            
            if event_type in EVENT_REGISTRY:
                event_class = EVENT_REGISTRY[event_type]
                event = event_class(**data)
                events.append(event)
        
        return events
    
    def subscribe(self, event_type: str, handler: Callable):
        """
        Subscribe handler to event type
        
        Args:
            event_type: Type of event to subscribe to
            handler: Async function to call when event occurs
        """
        
        if event_type not in self.subscriptions:
            self.subscriptions[event_type] = []
        
        self.subscriptions[event_type].append(handler)
        logger.info(f"Subscribed handler to {event_type}")
    
    def register_projection(self, projection):
        """Register a projection for event processing"""
        self.projections.append(projection)
        logger.info(f"Registered projection: {projection.__class__.__name__}")
    
    async def _trigger_subscriptions(self, event: DomainEvent):
        """Trigger all subscribers for this event type"""
        
        event_type = event.__class__.__name__
        handlers = self.subscriptions.get(event_type, [])
        
        for handler in handlers:
            try:
                if asyncio.iscoroutinefunction(handler):
                    await handler(event)
                else:
                    handler(event)
            except Exception as e:
                logger.error(f"Handler error for {event_type}: {str(e)}")
    
    async def _process_projections(self, event: DomainEvent):
        """Process event through all registered projections"""
        
        for projection in self.projections:
            try:
                if asyncio.iscoroutinefunction(projection.project):
                    await projection.project(event)
                else:
                    projection.project(event)
            except Exception as e:
                logger.error(f"Projection error: {str(e)}")
    
    async def replay_events(
        self,
        from_event_id: int = 0,
        to_event_id: Optional[int] = None
    ):
        """
        Replay events (for rebuilding projections or audit)
        
        Args:
            from_event_id: Start from this event ID
            to_event_id: End at this event ID (None = current)
        """
        
        query = """
            SELECT event_type, data, created_at
            FROM events
            WHERE id >= :from_id
        """
        
        params = {"from_id": from_event_id}
        
        if to_event_id:
            query += " AND id <= :to_id"
            params["to_id"] = to_event_id
        
        query += " ORDER BY id ASC"
        
        result = await self.db.execute(text(query), params)
        rows = result.fetchall()
        
        logger.info(f"Replaying {len(rows)} events")
        
        for row in rows:
            event_type = row[0]
            data = json.loads(row[1])
            
            if event_type in EVENT_REGISTRY:
                event_class = EVENT_REGISTRY[event_type]
                event = event_class(**data)
                
                # Process through projections
                await self._process_projections(event)
        
        logger.info("Event replay complete")
    
    async def get_event_statistics(self) -> Dict[str, Any]:
        """Get statistics about event store"""
        
        result = await self.db.execute(
            text("""
                SELECT 
                    event_type,
                    COUNT(*) as count,
                    MIN(created_at) as first_event,
                    MAX(created_at) as last_event
                FROM events
                GROUP BY event_type
                ORDER BY count DESC
            """)
        )
        
        stats = {}
        total = 0
        
        for row in result.fetchall():
            event_type = row[0]
            count = row[1]
            stats[event_type] = {
                "count": count,
                "first_event": row[2].isoformat() if row[2] else None,
                "last_event": row[3].isoformat() if row[3] else None,
            }
            total += count
        
        return {
            "total_events": total,
            "by_type": stats,
            "event_types": len(stats),
        }


class EventStoreFactory:
    """Factory for creating event store instances"""
    
    @staticmethod
    async def create(db_session: AsyncSession) -> EventStore:
        """Create and initialize event store"""
        
        store = EventStore(db_session)
        
        # Initialize event store tables if needed
        await store.db.execute(text("""
            CREATE TABLE IF NOT EXISTS events (
                id BIGSERIAL PRIMARY KEY,
                event_type TEXT NOT NULL,
                aggregate_id TEXT NOT NULL,
                aggregate_type TEXT NOT NULL,
                data JSONB NOT NULL,
                metadata JSONB,
                created_at TIMESTAMP NOT NULL DEFAULT NOW(),
                version INT NOT NULL,
                INDEX idx_aggregate (aggregate_id),
                INDEX idx_type (event_type),
                INDEX idx_time (created_at)
            )
        """))
        
        await store.db.commit()
        
        logger.info("Event store initialized")
        return store
