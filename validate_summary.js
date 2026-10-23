// node validate_summary.js
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
const invalidFiles = [];

for (const file of files) {
  const filePath = path.join(flowsDir, file);

  try {
    const data = JSON.parse(fs.readFileSync(filePath, "utf8"));

    if (validate(data)) {
      console.log(`✅ ${file}`);
      validCount++;
    } else {
      console.log(`❌ ${file} (${validate.errors.length} errors)`);
      invalidFiles.push({ file, errors: validate.errors });
      invalidCount++;
    }
  } catch (error) {
    console.log(`❌ ${file} (parse error)`);
    invalidFiles.push({ file, errors: [error.message] });
    invalidCount++;
  }
}

console.log("=".repeat(60));
console.log(`📊 Summary: ${validCount} valid, ${invalidCount} invalid`);

if (invalidCount > 0) {
  console.log(`\n❌ Invalid files:`);
  invalidFiles.forEach(({ file, errors }) => {
    console.log(`\n📄 ${file}:`);
    if (Array.isArray(errors) && errors[0] && typeof errors[0] === 'object') {
      // AJV errors
      const uniqueMessages = [...new Set(errors.map(e => e.message))];
      uniqueMessages.slice(0, 3).forEach(msg => {
        console.log(`   • ${msg}`);
      });
      if (uniqueMessages.length > 3) {
        console.log(`   • ... and ${uniqueMessages.length - 3} more error types`);
      }
    } else {
      // Parse errors
      errors.slice(0, 3).forEach(error => {
        console.log(`   • ${error}`);
      });
    }
  });
}

if (invalidCount === 0) {
  console.log("🎉 All workflows are valid!");
} else {
  console.log(`\n⚠️  ${invalidCount} workflow(s) need attention`);
}