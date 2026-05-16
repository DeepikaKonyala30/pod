"""
PodMind — Multi-Agent AI Framework Package

Specialized AI agents for resource-domain analysis, each consuming
normalized metrics and producing structured Pydantic output.

Agents:
    - cpu_agent: Isolation Forest + Z-score + throttle + gradient analysis
    - memory_agent: Linear regression leak detection + OOM risk + cache pressure
    - storage_agent: PVC saturation + restart correlation + bulk write detection
    - network_agent: Network saturation + chatty pods + log error rate

Infrastructure:
    - orchestrator: LangGraph DAG for parallel agent execution
    - dependency_mapper: Granger causality + NetworkX graph builder
    - forecaster: Prophet/ARIMA per-pod 60-minute forecasting
    - schemas: Pydantic models for all agent inputs and outputs
"""
