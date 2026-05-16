"""
PodMind — Collector Package

Async data collection service that pulls metrics from Prometheus, kubelet,
and the Kubernetes API, normalizes them, and writes to Redis TimeSeries.

Components:
    - k8s_client: Pod, PVC, event, log discovery via kubernetes-python SDK
    - prometheus_client: PromQL query executor with DataFrame output
    - kubelet_client: /stats/summary API client for PVC IOPS
    - log_collector: Async pod log streaming (last 100 lines)
    - normalizer: Metric normalization and 5s resampling with forward-fill
    - redis_writer: TimeSeries + Stream writer with retention policies
"""
