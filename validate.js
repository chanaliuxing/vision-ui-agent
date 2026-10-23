// node validate.js path/to/workflow.json
import fs from "fs";
import Ajv from "ajv";
import addFormats from "ajv-formats";

const schema = JSON.parse(fs.readFileSync("./schema/workflow.schema.json","utf8"));
const data = JSON.parse(fs.readFileSync(process.argv[2],"utf8"));

const ajv = new Ajv({ allErrors:true, strict:false });
addFormats(ajv);
const validate = ajv.compile(schema);

if (validate(data)) {
  console.log("✅ Valid workflow");
} else {
  console.error("❌ Invalid workflow:\n", ajv.errorsText(validate.errors,{ separator:"\n- " }));
  process.exit(1);
}
