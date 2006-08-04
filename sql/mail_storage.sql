CREATE TABLE "mail_storage" (
	"year" smallint,
	"pid" integer,
	"message_id" character(508),
	"mail" text
);

CREATE INDEX index_pidb ON mail_storage USING btree ("year", pid);
CREATE INDEX index_pidh ON mail_storage USING hash (pid);
CREATE INDEX index_message_idb ON mail_storage USING btree (message_id);
