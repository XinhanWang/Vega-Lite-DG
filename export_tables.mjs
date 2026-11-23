import {createRequire} from 'node:module';
import fs from 'node:fs';
import path from 'node:path';
import {pathToFileURL} from 'node:url';

const require = createRequire(import.meta.url);
const {exportTables} = require('./vendor/vega-lite-table-export/vega-lite-table-export.js');

export function writeTables(directory, compact) {
  const tables = exportTables(compact);
  for (const {id, markdown, csv} of tables) {
    if (!/^[a-zA-Z0-9_-]+$/.test(id)) throw new Error('Invalid artifact filename for table ' + id);
    for (const [extension, contents] of [['md', markdown], ['csv', csv]]) {
      const file = path.join(directory, id + '.' + extension);
      fs.writeFileSync(file + '.tmp', contents);
      fs.renameSync(file + '.tmp', file);
    }
  }
}

if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) {
  for (const directory of JSON.parse(fs.readFileSync(0, 'utf8'))) {
    const compact = JSON.parse(fs.readFileSync(path.join(directory, 'compact.vl.json'), 'utf8'));
    writeTables(directory, compact);
  }
}
