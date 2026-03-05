import fs from "fs";
import path from "path";

const p = path.join(process.cwd(), "data", "latentlab.sqlite");
if (fs.existsSync(p)) {
  fs.rmSync(p);
  console.log("Removed", p);
} else {
  console.log("No db found at", p);
}
