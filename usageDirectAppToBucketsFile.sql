##!/usr/bin/env nix-shell
##!nix-shell -i bash -p sqlite
#!/bin/bash

# run this as chmod +x ~/bin/usageDirectAppToBucketsFile.sql; ~/bin/usageDirectAppToBucketsFile.sql usageDirect-history.sqlite3
tail -n +9 "$0" | sqlite3 "$1"
exit $?

-- sql commands






.schema
-- 2440588 is the julian days at 1970-1-1 which is what usageDirect uses as its epoch;
-- 						discard ms, sec, keep mins as decimal
CREATE TEMP VIEW res AS 
	SELECT date(day + 2440588) as dayF, timeUsed / 1000 / 60 / 60.0 as hours, applicationId as id 
	FROM usageStats 
	WHERE 
		(id LIKE '%instagram%') AND 
		(date(dayF) <= date('now', '-1 day', 'localtime')) 
	ORDER BY day, applicationId;

SELECT date('now', '-1 day', 'localtime');

SELECT '\n';
.schema res
SELECT '\n';


CREATE TEMP VIEW costs AS
        SELECT dayF,  hours * 28 as dollars, concat('App Usage Contribution: ', id) as memo
	FROM res
	WHERE date('2025-08-11') <= dayF; -- initial is idk whatever out of sync or whatev


--						from			to
-- SELECT sum(dollars) from costs WHERE date('2025-07-30') <= dayF AND dayF <= date('2025-08-10');
-- initial is out of sync idk

.mode csv
SELECT 'Amount', 'Payee', 'Memo', 'Date Posted yyyy-mm-dd';
SELECT printf('%5.2f', dollars), 'Roth IRA', memo, dayF FROM costs;

.output usageDirectCostsOutput.tsv
SELECT 'Amount', 'Payee', 'Memo', 'Date Posted yyyy-mm-dd';
SELECT round(dollars, 2), 'Roth IRA', memo, dayF FROM costs;
