// node validate_all.js
import fs from "fs";
import path from "path";
import Ajv from "ajv";
import addFormats from "ajv-formats";

const schema = JSON.parse(fs.readFileSync("./schema/workflow.schema.json", "utf8"));
const ajv = new Ajv({ allErrors: true, strict: false });
addFormats(ajv);
const validate = ajv.compile(schema);

const flowsDir = "./flows";
const files = fs.readdirSync(flowsDir).filter(f => f.endsWith('.json'));

console.log(`🔍 Validating ${files.length} workflow files...`);
console.log("=".repeat(60));

let validCount = 0;
let invalidCount = 0;

for (const file of files) {
  const filePath = path.join(flowsDir, file);

  try {
    const data = JSON.parse(fs.readFileSync(filePath, "utf8"));

    if (validate(data)) {
      console.log(`✅ ${file}: Valid`);
      validCount++;
    } else {
      console.log(`❌ ${file}: Invalid`);
      console.log(`   ${ajv.errorsText(validate.errors, { separator: "\n   " })}`);
      console.log();
      invalidCount++;
    }
  } catch (error) {
    console.log(`❌ ${file}: Error reading file - ${error.message}`);
    invalidCount++;
  }
}

console.log("=".repeat(60));
console.log(`📊 Summary: ${validCount} valid, ${invalidCount} invalid`);

if (invalidCount === 0) {
  console.log("🎉 All workflows are valid!");
} else {
  console.log(`⚠️  ${invalidCount} workflow(s) need attention`);
  process.exit(1);
}