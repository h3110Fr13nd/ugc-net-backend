import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession
from app.db.models import Taxonomy, Question, QuestionTaxonomy

@pytest.mark.asyncio
async def test_recursive_taxonomy_filtering(client: AsyncClient, test_session: AsyncSession):
    # 1. Setup Taxonomy Hierarchy
    # Root
    root = Taxonomy(name="Root", node_type="unit", path="root")
    test_session.add(root)
    await test_session.flush()
    root.path = str(root.id)
    
    # Child
    child = Taxonomy(name="Child", node_type="topic", parent_id=root.id)
    test_session.add(child)
    await test_session.flush()
    child.path = f"{root.path}.{child.id}"
    
    # Grandchild
    grandchild = Taxonomy(name="Grandchild", node_type="subtopic", parent_id=child.id)
    test_session.add(grandchild)
    await test_session.flush()
    grandchild.path = f"{child.path}.{grandchild.id}"
    
    await test_session.commit()
    
    # 2. Create Questions
    # Q1 -> Root
    q1 = Question(title="Q1 Root", answer_type="text")
    test_session.add(q1)
    await test_session.flush()
    test_session.add(QuestionTaxonomy(question_id=q1.id, taxonomy_id=root.id))
    
    # Q2 -> Child
    q2 = Question(title="Q2 Child", answer_type="text")
    test_session.add(q2)
    await test_session.flush()
    test_session.add(QuestionTaxonomy(question_id=q2.id, taxonomy_id=child.id))
    
    # Q3 -> Grandchild
    q3 = Question(title="Q3 Grandchild", answer_type="text")
    test_session.add(q3)
    await test_session.flush()
    test_session.add(QuestionTaxonomy(question_id=q3.id, taxonomy_id=grandchild.id))
    
    await test_session.commit()
    
    # 3. Test Filtering
    
    # Filter by Root -> Should get Q1, Q2, Q3
    resp = await client.get(f"/api/v1/questions?taxonomy_id={root.id}")
    assert resp.status_code == 200
    data = resp.json()
    print(f"DEBUG: Root Filter Data: {data}")
    assert data["total"] == 3
    ids = {q["id"] for q in data["questions"]}
    assert str(q1.id) in ids
    assert str(q2.id) in ids
    assert str(q3.id) in ids
    
    # Filter by Child -> Should get Q2, Q3
    resp = await client.get(f"/api/v1/questions?taxonomy_id={child.id}")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 2
    ids = {q["id"] for q in data["questions"]}
    assert str(q1.id) not in ids
    assert str(q2.id) in ids
    assert str(q3.id) in ids
    
    # Filter by Grandchild -> Should get Q3
    resp = await client.get(f"/api/v1/questions?taxonomy_id={grandchild.id}")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 1
    ids = {q["id"] for q in data["questions"]}
    assert str(q3.id) in ids
