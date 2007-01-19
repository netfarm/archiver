CREATE TABLE mail_storage (
	year smallint NOT NULL,
	pid integer NOT NULL,
	mail text
);

CREATE INDEX index_pidb ON mail_storage USING btree (year);
CREATE INDEX index_pidh ON mail_storage USING btree (pid);
