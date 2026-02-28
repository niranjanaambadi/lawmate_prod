# backend/app/db/seed.py

"""
Database Seeding Script

Creates test data for development and testing.
"""

from sqlalchemy.orm import Session
from datetime import datetime, timedelta
import uuid
import random
from typing import List
from database import SessionLocal, engine, Base
from models import (
    User, Case, Document, CaseHistory, AIAnalysis,
    UserRole, CaseStatus, CasePartyRole, DocumentCategory, 
    CaseEventType, AIAnalysisStatus, UrgencyLevel
)
#from app.core.security import get_password_hash

# ============================================================================
# Seed Data
# ============================================================================

def create_test_user(db: Session) -> User:
    """Create test user"""
    user = User(
        id=uuid.uuid4(),
        email="testlawmate@gmail.com",
        mobile="9876543210",
        password_hash="testpassword",
        khc_advocate_id="KHC/TEST/001",
        khc_advocate_name="Test Advocate",
        khc_enrollment_number="K/12345/2020",
        role=UserRole.ADVOCATE,
        is_active=True,
        is_verified=True,
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
        preferences={
            "notification_email": True,
            "auto_sync": True,
            "theme": "light",
            "language": "en"
        }
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    print(f"✅ Created test user: {user.email}")
    return user

def create_sample_cases(db: Session, user: User, count: int = 10) -> List[Case]:
    """Create sample cases"""
    cases = []
    
    case_types = ["WP(C)", "CRL.A", "OP", "AS", "MFA"]
    statuses = [CaseStatus.FILED, CaseStatus.REGISTERED, CaseStatus.PENDING]
    party_roles = [CasePartyRole.PETITIONER, CasePartyRole.RESPONDENT]
    
    petitioner_names = [
        "John Doe", "Jane Smith", "Rajesh Kumar", "Priya Menon",
        "ABC Private Ltd", "XYZ Corporation", "State Bank of India"
    ]
    
    respondent_names = [
        "State of Kerala", "Union of India", "Kerala State Road Transport Corporation",
        "Municipal Corporation", "Richard Roe", "Acme Inc"
    ]
    
    for i in range(count):
        case_type = random.choice(case_types)
        case_year = random.choice([2024, 2025, 2026])
        case_num = random.randint(100, 9999)
        
        filing_date = datetime.utcnow() - timedelta(days=random.randint(1, 365))
        next_hearing = filing_date + timedelta(days=random.randint(30, 90))
        
        case = Case(
            id=uuid.uuid4(),
            advocate_id=user.id,
            case_number=f"{case_type} {case_num}/{case_year}",
            efiling_number=f"EKHC/{case_year}/{case_type.replace('(', '').replace(')', '')}/{case_num:05d}",
            case_type=case_type,
            case_year=case_year,
            party_role=random.choice(party_roles),
            petitioner_name=random.choice(petitioner_names),
            respondent_name=random.choice(respondent_names),
            efiling_date=filing_date,
            efiling_details=f"Sample case details for {case_type} case",
            bench_type=random.choice(["Single Bench", "Division Bench"]),
            judge_name=random.choice([
                "Justice A.K. Jayasankaran Nambiar",
                "Justice Devan Ramachandran",
                "Justice P.V. Kunhikrishnan"
            ]),
            status=random.choice(statuses),
            next_hearing_date=next_hearing if random.random() > 0.3 else None,
            khc_source_url="https://efiling.highcourtofkerala.nic.in/my_cases",
            last_synced_at=datetime.utcnow(),
            sync_status="completed",
            is_visible=True,
            created_at=filing_date,
            updated_at=datetime.utcnow()
        )
        db.add(case)
        cases.append(case)
    
    db.commit()
    print(f"✅ Created {count} sample cases")
    return cases

def create_sample_documents(db: Session, cases: List[Case]) -> List[Document]:
    """Create sample documents for cases"""
    documents = []
    
    doc_categories = [
        DocumentCategory.CASE_FILE,
        DocumentCategory.AFFIRMATION,
        DocumentCategory.ANNEXURE,
        DocumentCategory.RECEIPT
    ]
    
    for case in cases:
        # Create 2-5 documents per case
        num_docs = random.randint(2, 5)
        
        for i in range(num_docs):
            category = random.choice(doc_categories)
            doc_id = f"DOC{random.randint(1000, 9999)}"
            
            document = Document(
                id=uuid.uuid4(),
                case_id=case.id,
                khc_document_id=doc_id,
                category=category,
                title=f"{category.value.replace('_', ' ').title()} - {case.case_number}",
                description=f"Sample {category.value} document",
                s3_key=f"{case.advocate.khc_advocate_id}/{case.case_number}/{category.value}/{doc_id}.pdf",
                s3_bucket="lawmate-case-pdfs",
                file_size=random.randint(100000, 5000000),
                content_type="application/pdf",
                upload_status="completed",
                uploaded_at=case.created_at + timedelta(hours=random.randint(1, 24)),
                source_url=f"https://efiling.highcourtofkerala.nic.in/docs/{doc_id}.pdf",
                is_ocr_required=random.choice([True, False]),
                ocr_status="completed" if random.random() > 0.5 else "not_required",
                created_at=case.created_at + timedelta(hours=random.randint(1, 24)),
                updated_at=datetime.utcnow()
            )
            db.add(document)
            documents.append(document)
    
    db.commit()
    print(f"✅ Created {len(documents)} sample documents")
    return documents

def create_case_history(db: Session, cases: List[Case]) -> List[CaseHistory]:
    """Create case history entries"""
    history_entries = []
    
    event_types = [
        CaseEventType.FILED,
        CaseEventType.REGISTERED,
        CaseEventType.HEARING,
        CaseEventType.ADJOURNED
    ]
    
    for case in cases:
        # Create 2-4 history entries per case
        num_events = random.randint(2, 4)
        event_date = case.efiling_date
        
        for i in range(num_events):
            event_type = event_types[min(i, len(event_types) - 1)]
            
            history = CaseHistory(
                id=uuid.uuid4(),
                case_id=case.id,
                event_type=event_type,
                event_date=event_date,
                business_recorded=f"{event_type.value.replace('_', ' ').title()} - Sample entry",
                judge_name=case.judge_name,
                bench_type=case.bench_type,
                next_hearing_date=event_date + timedelta(days=30) if i < num_events - 1 else case.next_hearing_date,
                created_at=event_date
            )
            db.add(history)
            history_entries.append(history)
            
            event_date += timedelta(days=random.randint(20, 45))
    
    db.commit()
    print(f"✅ Created {len(history_entries)} case history entries")
    return history_entries

def create_ai_analyses(db: Session, cases: List[Case]) -> List[AIAnalysis]:
    """Create AI analysis records"""
    analyses = []
    
    for case in cases[:5]:  # Only analyze first 5 cases
        analysis = AIAnalysis(
            id=uuid.uuid4(),
            case_id=case.id,
            advocate_id=case.advocate_id,
            status=AIAnalysisStatus.COMPLETED,
            model_version="claude-3.5-sonnet-20241022",
            analysis={
                "case_type_classification": f"{case.case_type} - Article 226",
                "key_legal_issues": [
                    "Challenge to administrative order",
                    "Violation of principles of natural justice",
                    "Question of locus standi"
                ],
                "relevant_statutes": [
                    "Article 226 of Constitution of India",
                    "Administrative Tribunals Act, 1985"
                ],
                "precedent_cases": [
                    {
                        "name": "Sample Case v. State",
                        "citation": "AIR 2020 SC 100",
                        "relevance": "Interpretation of Article 226"
                    }
                ],
                "action_items": [
                    "File counter-affidavit within 4 weeks",
                    "Prepare case law compilation"
                ],
                "urgency_level": random.choice(["high", "medium", "low"]),
                "deadline_reminders": [
                    {
                        "task": "File counter-affidavit",
                        "due_date": (datetime.utcnow() + timedelta(days=28)).isoformat(),
                        "priority": "high"
                    }
                ],
                "case_summary": f"Brief summary of {case.case_number}"
            },
            urgency_level=random.choice([UrgencyLevel.HIGH, UrgencyLevel.MEDIUM, UrgencyLevel.LOW]),
            case_summary=f"AI-generated summary for {case.case_number}",
            processed_at=datetime.utcnow() - timedelta(hours=random.randint(1, 48)),
            processing_time_seconds=random.randint(30, 120),
            token_count=random.randint(2000, 5000),
            created_at=case.created_at + timedelta(days=1),
            updated_at=datetime.utcnow()
        )
        db.add(analysis)
        analyses.append(analysis)
    
    db.commit()
    print(f"✅ Created {len(analyses)} AI analyses")
    return analyses

# ============================================================================
# Main Seed Function
# ============================================================================

def seed_database():
    """
    Main seeding function.
    Creates all test data.
    """
    print("\n" + "=" * 80)
    print("🌱 Seeding Lawmate Database")
    print("=" * 80 + "\n")
    
    # Create tables
    print("📋 Creating database tables...")
    Base.metadata.create_all(bind=engine)
    print("✅ Tables created\n")
    
    # Get database session
    db = SessionLocal()
    
    try:
        # Check if data already exists
        existing_users = db.query(User).count()
        if existing_users > 0:
            print("⚠️  Database already contains data!")
            response = input("Do you want to clear and reseed? (yes/no): ")
            if response.lower() != 'yes':
                print("❌ Seeding cancelled")
                return
            
            print("🗑️  Clearing existing data...")
            Base.metadata.drop_all(bind=engine)
            Base.metadata.create_all(bind=engine)
            print("✅ Database cleared\n")
        
        # Create test data
        print("👤 Creating test user...")
        user = create_test_user(db)
        
        print("\n📁 Creating sample cases...")
        cases = create_sample_cases(db, user, count=10)
        
        print("\n📄 Creating sample documents...")
        documents = create_sample_documents(db, cases)
        
        print("\n📜 Creating case history...")
        history = create_case_history(db, cases)
        
        print("\n🤖 Creating AI analyses...")
        analyses = create_ai_analyses(db, cases)
        
        print("\n" + "=" * 80)
        print("✅ Database seeding completed successfully!")
        print("=" * 80)
        print(f"\n📊 Summary:")
        print(f"   • Users: 1")
        print(f"   • Cases: {len(cases)}")
        print(f"   • Documents: {len(documents)}")
        print(f"   • History Entries: {len(history)}")
        print(f"   • AI Analyses: {len(analyses)}")
        print(f"\n🔑 Test Credentials:")
        print(f"   Email: testlawmate@gmail.com")
        print(f"   Password: testpassword")
        print(f"   KHC ID: KHC/TEST/001")
        print("\n")
        
    except Exception as e:
        print(f"\n❌ Seeding failed: {str(e)}")
        db.rollback()
        raise
    finally:
        db.close()

# ============================================================================
# CLI Entry Point
# ============================================================================

if __name__ == "__main__":
    seed_database()