from __future__ import annotations
import threading,time,uuid
class JobRegistry:
    def __init__(self): self._lock=threading.Lock(); self._jobs:dict[str,dict]={}
    def create(self,kind:str,meta:dict|None=None)->str:
        job_id=uuid.uuid4().hex
        with self._lock: self._jobs[job_id]={"id":job_id,"kind":kind,"status":"queued","created_at":time.time(),"updated_at":time.time(),"meta":meta or {},"progress":{},"result":None,"error":None}
        return job_id
    def update(self,job_id:str,**changes)->None:
        with self._lock:
            job=self._jobs.get(job_id)
            if not job:return
            job.update(changes); job["updated_at"]=time.time()
    def progress(self,job_id:str,payload:dict)->None:self.update(job_id,status="running",progress=payload)
    def finish(self,job_id:str,result:dict)->None:self.update(job_id,status="done",result=result)
    def fail(self,job_id:str,error:str)->None:self.update(job_id,status="error",error=error)
    def get(self,job_id:str)->dict|None:
        with self._lock:
            job=self._jobs.get(job_id); return dict(job) if job else None
    def cleanup(self,max_age_seconds:int=86400)->int:
        now=time.time()
        with self._lock:
            old=[k for k,v in self._jobs.items() if now-v.get("updated_at",now)>max_age_seconds]
            for k in old:self._jobs.pop(k,None)
            return len(old)
