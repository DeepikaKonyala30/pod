import { useEffect, useRef } from 'react';
import * as d3 from 'd3';
import type { DependencyGraph as GraphData } from '../../types';

export function DependencyGraph({ graph }: { graph: GraphData | null }) {
  const svgRef = useRef<SVGSVGElement>(null);
  const containerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!graph || !svgRef.current || !containerRef.current) return;
    if (graph.nodes.length === 0) return;

    const width = containerRef.current.clientWidth;
    const height = containerRef.current.clientHeight;

    const svg = d3.select(svgRef.current);
    svg.selectAll("*").remove();

    // Map data for D3
    const nodes = graph.nodes.map(d => ({ ...d }));
    const edges = graph.edges.map(d => ({ ...d }));

    const colorMap = {
      healthy: 'var(--status-info)',
      warning: 'var(--status-high)',
      critical: 'var(--status-critical)',
    };

    const simulation = d3.forceSimulation(nodes as any)
      .force("link", d3.forceLink(edges).id((d: any) => d.id).distance(150))
      .force("charge", d3.forceManyBody().strength(-300))
      .force("center", d3.forceCenter(width / 2, height / 2))
      .force("collide", d3.forceCollide().radius(40));

    // Arrow marker
    svg.append("defs").selectAll("marker")
      .data(["end"])
      .enter().append("marker")
      .attr("id", "arrow")
      .attr("viewBox", "0 -5 10 10")
      .attr("refX", 25)
      .attr("refY", 0)
      .attr("markerWidth", 6)
      .attr("markerHeight", 6)
      .attr("orient", "auto")
      .append("path")
      .attr("fill", "var(--text-muted)")
      .attr("d", "M0,-5L10,0L0,5");

    // Edges
    const link = svg.append("g")
      .selectAll("line")
      .data(edges)
      .enter().append("line")
      .attr("stroke", "var(--text-muted)")
      .attr("stroke-width", (d) => Math.max(1, (d as any).r_squared * 5))
      .attr("marker-end", "url(#arrow)");

    // Nodes
    const node = svg.append("g")
      .selectAll("g")
      .data(nodes)
      .enter().append("g")
      .call(d3.drag<any, any>()
        .on("start", (event, d) => {
          if (!event.active) simulation.alphaTarget(0.3).restart();
          d.fx = d.x; d.fy = d.y;
        })
        .on("drag", (event, d) => {
          d.fx = event.x; d.fy = event.y;
        })
        .on("end", (event, d) => {
          if (!event.active) simulation.alphaTarget(0);
          d.fx = null; d.fy = null;
        }));

    // Node circles
    node.append("circle")
      .attr("r", 20)
      .attr("fill", "var(--bg-surface)")
      .attr("stroke", (d) => colorMap[d.status])
      .attr("stroke-width", 2);

    // Node inner pressure indicator
    node.append("circle")
      .attr("r", (d) => 18 * d.resource_pressure)
      .attr("fill", (d) => colorMap[d.status])
      .attr("opacity", 0.3);

    // Node labels
    node.append("text")
      .text((d) => d.pod)
      .attr("x", 0)
      .attr("y", 35)
      .attr("text-anchor", "middle")
      .attr("fill", "var(--text-primary)")
      .style("font-size", "12px")
      .style("font-family", "JetBrains Mono");

    // Edge labels
    const edgeLabels = svg.append("g")
      .selectAll("text")
      .data(edges)
      .enter().append("text")
      .text((d) => `${d.resource_type} (lag ${d.lag_seconds}s)`)
      .attr("fill", "var(--text-secondary)")
      .style("font-size", "10px")
      .attr("text-anchor", "middle");

    simulation.on("tick", () => {
      link
        .attr("x1", (d: any) => d.source.x)
        .attr("y1", (d: any) => d.source.y)
        .attr("x2", (d: any) => d.target.x)
        .attr("y2", (d: any) => d.target.y);

      node.attr("transform", (d: any) => `translate(${d.x},${d.y})`);

      edgeLabels
        .attr("x", (d: any) => (d.source.x + d.target.x) / 2)
        .attr("y", (d: any) => (d.source.y + d.target.y) / 2 - 5);
    });

    return () => {
      simulation.stop();
    };
  }, [graph]);

  if (!graph || graph.nodes.length === 0) {
    return (
      <div className="glass-panel" style={{ flex: 1, display: 'flex', alignItems: 'center', justifyContent: 'center', color: 'var(--text-muted)' }}>
        No significant dependencies detected.
      </div>
    );
  }

  return (
    <div className="glass-panel" style={{ flex: 1, position: 'relative' }} ref={containerRef}>
      <h3 style={{ position: 'absolute', top: 20, left: 20, fontSize: '1rem', color: 'var(--text-primary)' }}>
        Granger Causality Graph
      </h3>
      <svg ref={svgRef} style={{ width: '100%', height: '100%' }} />
    </div>
  );
}
