import Ajv from 'ajv';
import addFormats from 'ajv-formats';
import { readFileSync } from 'fs';
import { join, dirname } from 'path';
import { fileURLToPath } from 'url';

const __filename = fileURLToPath(import.meta.url);
const __dirname = dirname(__filename);

// Initialize Ajv with proper configuration
export function createAjvInstance(): Ajv {
  const ajv = new Ajv({
    allErrors: true,
    verbose: true,
    strict: false,
    allowUnionTypes: true
  });

  // Add format validators
  addFormats(ajv);

  return ajv;
}

// Load workflow schema
export function loadWorkflowSchema(): any {
  const schemaPath = join(__dirname, '../../../schemas/workflow.schema.json');
  const schemaContent = readFileSync(schemaPath, 'utf-8');
  return JSON.parse(schemaContent);
}

// Load action schemas from the registry
export function loadActionSchemas(): Record<string, any> {
  const actionSchemas: Record<string, any> = {};

  try {
    // Load individual action schemas
    const actionsDir = join(__dirname, '../../../schemas/actions');
    const actionFiles = [
      'ext.open_url.json',
      'ext.click.json',
      'vision.find_element.json',
      'llm.plan.json',
      'llm.reply.json'
    ];

    for (const file of actionFiles) {
      try {
        const actionPath = join(actionsDir, file);
        const actionContent = readFileSync(actionPath, 'utf-8');
        const actionDef = JSON.parse(actionContent);
        actionSchemas[actionDef.id] = actionDef;
      } catch (error) {
        console.warn(`Failed to load action schema ${file}:`, error);
      }
    }
  } catch (error) {
    console.error('Failed to load action schemas:', error);
  }

  return actionSchemas;
}

// Create validator instance with all schemas
export function createValidator() {
  const ajv = createAjvInstance();
  const workflowSchema = loadWorkflowSchema();
  const actionSchemas = loadActionSchemas();

  // Add workflow schema
  const validateWorkflow = ajv.compile(workflowSchema);

  return {
    ajv,
    validateWorkflow,
    actionSchemas,
    workflowSchema
  };
}