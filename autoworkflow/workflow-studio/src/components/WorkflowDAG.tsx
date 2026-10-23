// M2: Frontend Studio - Workflow DAG Visualization with XYFlow
"use client";

import React, { useCallback, useMemo } from 'react';
import {
  ReactFlow,
  Node,
  Edge,
  addEdge,
  Background,
  Controls,
  MiniMap,
  useNodesState,
  useEdgesState,
  Connection,
  NodeTypes,
  Panel
} from '@xyflow/react';
import '@xyflow/react/dist/style.css';
import type { WorkflowDefinition, WorkflowStep, WorkflowEdge } from '@/lib/types';

interface WorkflowDAGProps {
  workflow: WorkflowDefinition;
  selectedStepId?: string | null;
  onStepSelect: (stepId: string | null) => void;
  onStepUpdate: (stepId: string, updates: Partial<WorkflowStep>) => void;
  onEdgeAdd: (edge: WorkflowEdge) => void;
  onEdgeRemove: (edgeId: string) => void;
  readOnly?: boolean;
  className?: string;
}

// Custom Node Component for Workflow Steps
const WorkflowStepNode: React.FC<{
  data: {
    step: WorkflowStep;
    isSelected: boolean;
    isStart: boolean;
    onSelect: (stepId: string) => void;
  };
}> = ({ data }) => {
  const { step, isSelected, isStart, onSelect } = data;

  const nodeTypeColors = {
    action: 'bg-blue-100 border-blue-300',
    branch: 'bg-yellow-100 border-yellow-300',
    loop: 'bg-green-100 border-green-300',
    parallel: 'bg-purple-100 border-purple-300',
    wait: 'bg-gray-100 border-gray-300',
    subflow: 'bg-indigo-100 border-indigo-300',
    human_input: 'bg-pink-100 border-pink-300'
  };

  const baseClass = nodeTypeColors[step.type] || 'bg-gray-100 border-gray-300';
  const selectedClass = isSelected ? 'ring-2 ring-blue-500' : '';
  const startClass = isStart ? 'ring-2 ring-green-500' : '';

  return (
    <div
      onClick={() => onSelect(step.id)}
      className={`
        px-4 py-2 border-2 rounded-lg cursor-pointer min-w-[160px] text-center
        ${baseClass} ${selectedClass} ${startClass}
        hover:shadow-lg transition-all duration-200
      `}
    >
      {/* Header */}
      <div className="font-medium text-sm mb-1">
        {step.name || step.id}
        {isStart && (
          <span className="ml-2 px-1 py-0.5 text-xs bg-green-200 text-green-800 rounded">
            START
          </span>
        )}
      </div>

      {/* Type Badge */}
      <div className="text-xs text-gray-600 mb-1">
        {step.type}
      </div>

      {/* Action Info */}
      {step.uses && (
        <div className="text-xs text-gray-500 truncate">
          {step.uses}
        </div>
      )}

      {/* Handles for connections */}
      <div className="absolute -top-1 left-1/2 transform -translate-x-1/2 w-2 h-2 bg-gray-400 rounded-full opacity-0 group-hover:opacity-100" />
      <div className="absolute -bottom-1 left-1/2 transform -translate-x-1/2 w-2 h-2 bg-gray-400 rounded-full opacity-0 group-hover:opacity-100" />
    </div>
  );
};

const nodeTypes: NodeTypes = {
  workflowStep: WorkflowStepNode
};

export const WorkflowDAG: React.FC<WorkflowDAGProps> = ({
  workflow,
  selectedStepId,
  onStepSelect,
  onStepUpdate,
  onEdgeAdd,
  onEdgeRemove,
  readOnly = false,
  className = ''
}) => {
  // Convert workflow to DAG nodes and edges
  const { nodes: initialNodes, edges: initialEdges } = useMemo(() => {
    const nodes: Node[] = [];
    const edges: Edge[] = [];

    if (!workflow.steps || !Array.isArray(workflow.steps)) {
      return { nodes, edges };
    }

    // Auto-layout positions
    const stepPositions = workflow.steps.reduce((acc, step, index) => {
      const x = (index % 4) * 200;
      const y = Math.floor(index / 4) * 100;
      acc[step.id] = { x, y };
      return acc;
    }, {} as Record<string, { x: number; y: number }>);

    // Create nodes
    workflow.steps.forEach((step, index) => {
      const position = stepPositions[step.id] || { x: 0, y: 0 };

      nodes.push({
        id: step.id,
        type: 'workflowStep',
        position,
        data: {
          step,
          isSelected: step.id === selectedStepId,
          isStart: step.id === workflow.start,
          onSelect: onStepSelect
        }
      });
    });

    // Create edges from workflow edges
    if (workflow.edges && Array.isArray(workflow.edges)) {
      workflow.edges.forEach((edge, index) => {
        edges.push({
          id: `edge-${edge.from}-${edge.to}`,
          source: edge.from,
          target: edge.to,
          label: edge.condition || edge.label,
          type: 'smoothstep',
          animated: false
        });
      });
    }

    // Create implicit sequential edges if no explicit edges
    if (edges.length === 0 && workflow.steps.length > 1) {
      for (let i = 0; i < workflow.steps.length - 1; i++) {
        edges.push({
          id: `seq-${workflow.steps[i].id}-${workflow.steps[i + 1].id}`,
          source: workflow.steps[i].id,
          target: workflow.steps[i + 1].id,
          type: 'smoothstep',
          animated: false,
          style: { strokeDasharray: '5,5' }
        });
      }
    }

    return { nodes, edges };
  }, [workflow, selectedStepId]);

  const [nodes, setNodes, onNodesChange] = useNodesState(initialNodes);
  const [edges, setEdges, onEdgesChange] = useEdgesState(initialEdges);

  // Handle new connections
  const onConnect = useCallback(
    (params: Connection) => {
      if (readOnly || !params.source || !params.target) return;

      const newEdge: WorkflowEdge = {
        from: params.source,
        to: params.target,
        condition: undefined,
        label: undefined
      };

      onEdgeAdd(newEdge);
      setEdges((eds) => addEdge(params, eds));
    },
    [readOnly, onEdgeAdd, setEdges]
  );

  // Handle edge deletion
  const onEdgesDelete = useCallback(
    (edgesToDelete: Edge[]) => {
      if (readOnly) return;

      edgesToDelete.forEach((edge) => {
        onEdgeRemove(edge.id);
      });
    },
    [readOnly, onEdgeRemove]
  );

  // Update node selection when prop changes
  React.useEffect(() => {
    setNodes((nds) =>
      nds.map((node) => ({
        ...node,
        data: {
          ...node.data,
          isSelected: node.id === selectedStepId
        }
      }))
    );
  }, [selectedStepId, setNodes]);

  const layoutNodes = useCallback(() => {
    // Simple auto-layout algorithm
    setNodes((nds) =>
      nds.map((node, index) => ({
        ...node,
        position: {
          x: (index % 4) * 220,
          y: Math.floor(index / 4) * 120
        }
      }))
    );
  }, [setNodes]);

  return (
    <div className={`relative h-full ${className}`}>
      <ReactFlow
        nodes={nodes}
        edges={edges}
        onNodesChange={onNodesChange}
        onEdgesChange={onEdgesChange}
        onConnect={onConnect}
        onEdgesDelete={onEdgesDelete}
        nodeTypes={nodeTypes}
        fitView
        attributionPosition="bottom-left"
        className="bg-gray-50"
      >
        <Background color="#e5e7eb" gap={16} />
        <Controls />
        <MiniMap
          nodeColor={(node) => {
            if (node.data.isStart) return '#10b981';
            if (node.data.isSelected) return '#3b82f6';
            return '#6b7280';
          }}
          nodeStrokeWidth={3}
          zoomable
          pannable
        />

        {/* Action Panel */}
        <Panel position="top-left" className="bg-white p-2 rounded shadow">
          <div className="flex flex-col space-y-2">
            <button
              onClick={layoutNodes}
              className="px-3 py-1 text-sm bg-blue-100 text-blue-800 rounded hover:bg-blue-200"
            >
              Auto Layout
            </button>
            <div className="text-xs text-gray-500">
              Steps: {workflow.steps?.length || 0}
            </div>
            <div className="text-xs text-gray-500">
              Edges: {workflow.edges?.length || 0}
            </div>
          </div>
        </Panel>

        {/* Legend */}
        <Panel position="bottom-right" className="bg-white p-3 rounded shadow">
          <div className="text-sm font-medium mb-2">Step Types</div>
          <div className="space-y-1 text-xs">
            <div className="flex items-center space-x-2">
              <div className="w-3 h-3 bg-blue-100 border border-blue-300 rounded"></div>
              <span>Action</span>
            </div>
            <div className="flex items-center space-x-2">
              <div className="w-3 h-3 bg-yellow-100 border border-yellow-300 rounded"></div>
              <span>Branch</span>
            </div>
            <div className="flex items-center space-x-2">
              <div className="w-3 h-3 bg-green-100 border border-green-300 rounded"></div>
              <span>Loop</span>
            </div>
            <div className="flex items-center space-x-2">
              <div className="w-3 h-3 bg-purple-100 border border-purple-300 rounded"></div>
              <span>Parallel</span>
            </div>
          </div>
        </Panel>
      </ReactFlow>
    </div>
  );
};

export default WorkflowDAG;