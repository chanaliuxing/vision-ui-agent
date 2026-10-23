// M2: Frontend Studio - Monaco JSON Editor with Schema Support
"use client";

import React, { useRef, useEffect, useState } from 'react';
import * as monaco from 'monaco-editor';
import { Editor } from '@monaco-editor/react';
import type { WorkflowDefinition } from '@/lib/types';

interface JsonEditorProps {
  value: WorkflowDefinition;
  onChange: (value: WorkflowDefinition) => void;
  schema?: any;
  readOnly?: boolean;
  height?: string;
  className?: string;
}

export const JsonEditor: React.FC<JsonEditorProps> = ({
  value,
  onChange,
  schema,
  readOnly = false,
  height = '600px',
  className = ''
}) => {
  const editorRef = useRef<monaco.editor.IStandaloneCodeEditor | null>(null);
  const [jsonString, setJsonString] = useState(JSON.stringify(value, null, 2));

  // Configure Monaco Editor for JSON schema validation
  useEffect(() => {
    if (schema) {
      monaco.languages.json.jsonDefaults.setDiagnosticsOptions({
        validate: true,
        schemas: [{
          uri: 'http://workflow-schema.com/workflow.json',
          fileMatch: ['*'],
          schema: schema
        }]
      });
    }
  }, [schema]);

  const handleEditorDidMount = (editor: monaco.editor.IStandaloneCodeEditor) => {
    editorRef.current = editor;

    // Configure editor settings
    editor.updateOptions({
      minimap: { enabled: false },
      folding: true,
      lineNumbers: 'on',
      wordWrap: 'on',
      scrollBeyondLastLine: false,
      automaticLayout: true,
      tabSize: 2,
      insertSpaces: true,
      formatOnPaste: true,
      formatOnType: true
    });

    // Add custom keyboard shortcuts
    editor.addCommand(monaco.KeyMod.CtrlCmd | monaco.KeyCode.KeyS, () => {
      handleSave();
    });

    editor.addCommand(monaco.KeyMod.CtrlCmd | monaco.KeyMod.Shift | monaco.KeyCode.KeyF, () => {
      editor.getAction('editor.action.formatDocument')?.run();
    });
  };

  const handleSave = () => {
    try {
      const parsed = JSON.parse(jsonString);
      onChange(parsed);
    } catch (error) {
      console.error('Invalid JSON:', error);
    }
  };

  const handleValueChange = (value: string | undefined) => {
    if (value !== undefined) {
      setJsonString(value);

      // Auto-save valid JSON
      try {
        const parsed = JSON.parse(value);
        onChange(parsed);
      } catch (error) {
        // Invalid JSON - don't update the workflow
      }
    }
  };

  // Update editor content when value prop changes
  useEffect(() => {
    const newJsonString = JSON.stringify(value, null, 2);
    if (newJsonString !== jsonString) {
      setJsonString(newJsonString);
    }
  }, [value]);

  const formatJson = () => {
    if (editorRef.current) {
      editorRef.current.getAction('editor.action.formatDocument')?.run();
    }
  };

  const validateJson = () => {
    try {
      JSON.parse(jsonString);
      return true;
    } catch (error) {
      return false;
    }
  };

  return (
    <div className={`relative ${className}`}>
      {/* Toolbar */}
      <div className="flex items-center justify-between p-2 bg-gray-50 border-b">
        <div className="flex items-center space-x-2">
          <span className="text-sm font-medium text-gray-700">Workflow JSON</span>
          {!validateJson() && (
            <span className="px-2 py-1 text-xs bg-red-100 text-red-800 rounded">
              Invalid JSON
            </span>
          )}
        </div>
        <div className="flex items-center space-x-2">
          <button
            onClick={formatJson}
            className="px-3 py-1 text-xs bg-blue-100 text-blue-800 rounded hover:bg-blue-200"
            title="Format JSON (Ctrl+Shift+F)"
          >
            Format
          </button>
          <button
            onClick={handleSave}
            className="px-3 py-1 text-xs bg-green-100 text-green-800 rounded hover:bg-green-200"
            title="Save (Ctrl+S)"
          >
            Save
          </button>
        </div>
      </div>

      {/* Editor */}
      <Editor
        height={height}
        defaultLanguage="json"
        value={jsonString}
        onChange={handleValueChange}
        onMount={handleEditorDidMount}
        options={{
          readOnly,
          theme: 'vs-light',
          fontSize: 14,
          lineHeight: 20,
          scrollbar: {
            vertical: 'auto',
            horizontal: 'auto',
            verticalScrollbarSize: 12,
            horizontalScrollbarSize: 12
          }
        }}
      />
    </div>
  );
};

export default JsonEditor;