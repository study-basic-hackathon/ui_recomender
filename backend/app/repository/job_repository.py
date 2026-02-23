from uuid import UUID

from sqlalchemy.orm import Session

from app.model.job import Job, JobStatus


class JobRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def create(self, job: Job) -> Job:
        self.db.add(job)
        self.db.commit()
        self.db.refresh(job)
        return job

    def get_by_id(self, job_id: UUID) -> Job | None:
        return self.db.query(Job).filter(Job.id == job_id).first()

    def update_status(self, job_id: UUID, status: JobStatus, **kwargs: object) -> Job | None:
        job = self.get_by_id(job_id)
        if job:
            job.status = status
            for key, value in kwargs.items():
                if hasattr(job, key):
                    setattr(job, key, value)
            self.db.commit()
            self.db.refresh(job)
        return job

    def list_all(self) -> list[Job]:
        return self.db.query(Job).order_by(Job.created_at.desc()).all()
