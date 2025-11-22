import asyncio
import sys
import os
from sqlalchemy import select, func

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.db.base import AsyncSessionLocal
from app.db.models import Question, Taxonomy, QuestionTaxonomy

async def verify():
    async with AsyncSessionLocal() as session:
        q_count = await session.scalar(select(func.count(Question.id)))
        t_count = await session.scalar(select(func.count(Taxonomy.id)))
        qt_count = await session.scalar(select(func.count(QuestionTaxonomy.id)))
        
        print(f"Questions: {q_count}")
        print(f"Taxonomy Nodes: {t_count}")
        print(f"Question-Taxonomy Links: {qt_count}")

        # Check for multiple links
        stmt = select(QuestionTaxonomy.question_id, func.count(QuestionTaxonomy.taxonomy_id))\
            .group_by(QuestionTaxonomy.question_id)\
            .having(func.count(QuestionTaxonomy.taxonomy_id) > 1)
        result = await session.execute(stmt)
        multi_linked = result.all()
        print(f"Questions with >1 link: {len(multi_linked)}")

if __name__ == "__main__":
    asyncio.run(verify())
