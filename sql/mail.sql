CREATE TABLE "mail" (
	"year" smallint,
	"pid" integer,
	"from_login" character(28),
	"from_domain" character(255),
	"to_login" character(28),
	"to_domain" character(255),
	"subject" character(252),
	"mail_date" timestamp with time zone,
	"attachment" smallint
);

CREATE TABLE "mail_pid" (
	"pid" integer,
	"year" smallint
);

INSERT INTO mail_pid values(0, 2004);

CREATE INDEX index_pidb ON mail USING btree ("year", pid);
CREATE INDEX index_pidh ON mail USING hash (pid);
CREATE INDEX index_from_loginb ON mail USING btree (from_login);
CREATE INDEX index_from_domainb ON mail USING btree (from_domain);
CREATE INDEX index_fromb ON mail USING btree (from_domain, from_login);
CREATE INDEX index_to_loginb ON mail USING btree (to_login);
CREATE INDEX index_to_domainb ON mail USING btree (to_domain);
CREATE INDEX index_tob ON mail USING btree (to_domain, to_login);
CREATE INDEX index_mail_dateb ON mail USING btree (mail_date);
