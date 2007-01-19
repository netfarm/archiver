-- MAIL PID
CREATE TABLE mail_pid (
    year smallint NOT NULL,
    pid integer NOT NULL
);

CREATE TABLE mail (
    mail_id integer NOT NULL,
    year smallint NOT NULL,
    pid integer NOT NULL,
    message_id character varying(508) NOT NULL,
    from_login character varying(28) NOT NULL,
    from_domain character varying(255) NOT NULL,
    subject character varying(255) NOT NULL,
    mail_date date NOT NULL,
    attachment smallint DEFAULT 0 NOT NULL,
    media bigint DEFAULT -1
);

ALTER TABLE ONLY mail
    ADD CONSTRAINT mail_pkey PRIMARY KEY (mail_id);

CREATE SEQUENCE mail_id_sequence
    START WITH 1
    INCREMENT BY 1
    MINVALUE 1
    MAXVALUE 9223372036854775807
    CACHE 1;

-- RECIPIENT
CREATE TABLE recipient (
    mail_id integer NOT NULL,
    to_login character varying(28) NOT NULL,
    to_domain character varying(255) NOT NULL
);

ALTER TABLE ONLY recipient
    ADD CONSTRAINT recipient_mail_id_fkey FOREIGN KEY (mail_id)
    REFERENCES mail(mail_id) ON UPDATE CASCADE ON DELETE CASCADE;

-- AUTHORIZED
CREATE TABLE authorized (
    mail_id integer NOT NULL,
    mailbox character varying(28) NOT NULL
);

ALTER TABLE ONLY authorized
    ADD CONSTRAINT recipient_mail_id_fkey FOREIGN KEY (mail_id)
    REFERENCES mail(mail_id) ON UPDATE CASCADE ON DELETE CASCADE;

CREATE INDEX authorized_mail_id_index ON authorized USING btree (mail_id);
CREATE INDEX authorized_mailbox_index ON authorized USING btree (mailbox);

CREATE FUNCTION get_curr_year() RETURNS integer AS $$
SELECT int4(Extract(year from now())) as result from mail_pid limit 1;
$$ LANGUAGE sql;

INSERT INTO mail_pid (year, pid ) VALUES ( 0 , 0 );

CREATE FUNCTION get_curr_pid() RETURNS integer AS $$
SELECT pid as result from mail_pid limit 1;
$$ LANGUAGE sql;

CREATE FUNCTION get_new_pid() RETURNS integer AS $$
update mail_pid set
 pid = case when year = get_curr_year() then pid + 1 else 1 end ,
 year = get_curr_year();
SELECT pid as result from mail_pid limit 1;
$$ LANGUAGE sql;

CREATE FUNCTION get_next_mail_id() RETURNS bigint AS $$
SELECT nextval('mail_id_sequence') as result;
$$ LANGUAGE sql;

CREATE FUNCTION get_curr_mail_id() RETURNS bigint AS $$
SELECT currval('mail_id_sequence') as result;
$$ LANGUAGE sql;

CREATE INDEX year_index ON mail USING btree (year);
CREATE INDEX pid_index ON mail USING btree (pid);
CREATE INDEX message_id_index ON mail USING btree (message_id);
CREATE INDEX from_login_index ON mail USING btree (from_login);
CREATE INDEX from_domain_index ON mail USING btree (from_domain);
CREATE INDEX subject_index ON mail USING btree (subject);
CREATE INDEX mail_date_index ON mail USING btree (mail_date);
CREATE INDEX attachment_index ON mail USING btree (attachment);
CREATE INDEX media_index ON mail USING btree (media);
CREATE INDEX recipient_mail_id_index ON recipient USING btree (mail_id);
CREATE INDEX recipient_to_login_index ON recipient USING btree (to_login);
CREATE INDEX recipient_to_domain_index ON recipient USING btree (to_domain);

-- MAIL - RECIPIENT
CREATE OR REPLACE VIEW mail_recipient AS
 SELECT m.mail_id AS mail_id, m.year, m.pid, m.message_id,
         m.from_login, m.from_domain, r.to_login, r.to_domain,
         m.subject, m.mail_date, m.attachment, m.media
   FROM mail as m
   JOIN recipient as r ON m.mail_id = r.mail_id
 ORDER BY m.year, m.pid, r.to_login, r.to_domain;
